from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from core.utils.exceptions import OpenRAGError, ServiceUnavailableError
from services.inference._retry import _is_retryable, retry_after_seconds, with_retry


def _status_error(status: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "http://test")
    return httpx.HTTPStatusError("err", request=req, response=httpx.Response(status, request=req, headers=headers))


class TestIsRetryable:
    def test_timeout_exception(self):
        assert _is_retryable(httpx.ReadTimeout("timeout"))

    def test_connect_error(self):
        assert _is_retryable(httpx.ConnectError("refused"))

    @pytest.mark.parametrize("status", [429, 502, 503, 504])
    def test_retryable_http_status(self, status):
        req = httpx.Request("GET", "http://test")
        exc = httpx.HTTPStatusError("err", request=req, response=httpx.Response(status, request=req))
        assert _is_retryable(exc)

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 500])
    def test_non_retryable_http_status(self, status):
        req = httpx.Request("GET", "http://test")
        exc = httpx.HTTPStatusError("err", request=req, response=httpx.Response(status, request=req))
        assert not _is_retryable(exc)

    def test_openrag_error_retryable(self):
        assert _is_retryable(ServiceUnavailableError("down"))  # 503

    def test_openrag_error_non_retryable(self):
        assert not _is_retryable(OpenRAGError("bad", status_code=404))

    def test_unrelated_exception(self):
        assert not _is_retryable(ValueError("nope"))


class TestWithRetry:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        call_count = 0

        @with_retry(max_attempts=3, base_wait=0.01, max_wait=0.1)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_connect_error(self):
        call_count = 0

        @with_retry(max_attempts=3, base_wait=0.01, max_wait=0.1)
        async def fail_connect():
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("refused")

        with pytest.raises(httpx.ConnectError):
            await fail_connect()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_429(self):
        call_count = 0
        req = httpx.Request("GET", "http://test")

        @with_retry(max_attempts=3, base_wait=0.01, max_wait=0.1, rate_limit_attempts=3, rate_limit_max_wait=0.01)
        async def fail_429():
            nonlocal call_count
            call_count += 1
            raise httpx.HTTPStatusError("rate limited", request=req, response=httpx.Response(429, request=req))

        with pytest.raises(httpx.HTTPStatusError):
            await fail_429()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self):
        call_count = 0
        req = httpx.Request("GET", "http://test")

        @with_retry(max_attempts=3, base_wait=0.01, max_wait=0.1)
        async def fail_400():
            nonlocal call_count
            call_count += 1
            raise httpx.HTTPStatusError("bad request", request=req, response=httpx.Response(400, request=req))

        with pytest.raises(httpx.HTTPStatusError):
            await fail_400()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_succeeds_after_transient_failure(self):
        call_count = 0

        @with_retry(max_attempts=3, base_wait=0.01, max_wait=0.1)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("transient")
            return "recovered"

        result = await flaky()
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retries_openrag_503(self):
        call_count = 0

        @with_retry(max_attempts=3, base_wait=0.01, max_wait=0.1)
        async def fail_503():
            nonlocal call_count
            call_count += 1
            raise ServiceUnavailableError("down")

        with pytest.raises(ServiceUnavailableError):
            await fail_503()

        assert call_count == 3


class TestRetryAfter:
    def test_delta_seconds(self):
        assert retry_after_seconds(_status_error(429, {"Retry-After": "7"})) == 7.0

    def test_http_date(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        header = format_datetime(now + timedelta(seconds=30), usegmt=True)
        assert retry_after_seconds(_status_error(429, {"Retry-After": header}), now=now) == 30.0

    def test_date_in_the_past_is_zero(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        header = format_datetime(now - timedelta(seconds=30), usegmt=True)
        assert retry_after_seconds(_status_error(429, {"Retry-After": header}), now=now) == 0.0

    def test_absent_or_unreadable(self):
        assert retry_after_seconds(_status_error(429)) is None
        assert retry_after_seconds(_status_error(429, {"Retry-After": "soon"})) is None
        assert retry_after_seconds(ValueError("no response")) is None

    def test_found_through_the_translated_error(self):
        """Clients raise ``OpenRAGError(...) from httpx.HTTPStatusError``: the
        header must still be read from the cause."""
        cause = _status_error(429, {"Retry-After": "3"})
        try:
            raise OpenRAGError("LLM error (429)", status_code=429) from cause
        except OpenRAGError as exc:
            assert retry_after_seconds(exc) == 3.0


class TestRateLimitPolicy:
    @pytest.mark.asyncio
    async def test_429_gets_its_own_attempt_budget(self):
        calls = 0

        @with_retry(max_attempts=2, base_wait=0.01, max_wait=0.01, rate_limit_attempts=5, rate_limit_max_wait=0.01)
        async def always_429():
            nonlocal calls
            calls += 1
            raise OpenRAGError("LLM error (429)", status_code=429)

        with pytest.raises(OpenRAGError):
            await always_429()
        assert calls == 5

    @pytest.mark.asyncio
    async def test_5xx_keeps_the_short_budget(self):
        calls = 0

        @with_retry(max_attempts=2, base_wait=0.01, max_wait=0.01, rate_limit_attempts=5, rate_limit_max_wait=0.01)
        async def always_503():
            nonlocal calls
            calls += 1
            raise ServiceUnavailableError("down")

        with pytest.raises(ServiceUnavailableError):
            await always_503()
        assert calls == 2

    @pytest.mark.asyncio
    async def test_waits_for_retry_after_then_succeeds(self, monkeypatch):
        slept: list[float] = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        calls = 0

        @with_retry(max_attempts=3, base_wait=0.01, max_wait=0.1, rate_limit_attempts=3, rate_limit_max_wait=60)
        async def limited_once():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OpenRAGError("LLM error (429)", status_code=429) from _status_error(429, {"Retry-After": "2"})
            return "ok"

        assert await limited_once() == "ok"
        assert calls == 2
        assert len(slept) == 1 and 2.0 <= slept[0] <= 3.0

    @pytest.mark.asyncio
    async def test_retry_after_is_capped(self, monkeypatch):
        slept: list[float] = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr("asyncio.sleep", fake_sleep)
        calls = 0

        @with_retry(max_attempts=3, base_wait=0.01, max_wait=0.1, rate_limit_attempts=3, rate_limit_max_wait=5)
        async def limited_once():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _status_error(429, {"Retry-After": "3600"})
            return "ok"

        assert await limited_once() == "ok"
        assert slept and slept[0] <= 6.0

    @pytest.mark.asyncio
    async def test_rate_limit_budget_never_below_max_attempts(self):
        calls = 0

        @with_retry(max_attempts=4, base_wait=0.01, max_wait=0.01, rate_limit_attempts=2, rate_limit_max_wait=0.01)
        async def always_429():
            nonlocal calls
            calls += 1
            raise _status_error(429)

        with pytest.raises(httpx.HTTPStatusError):
            await always_429()
        assert calls == 4
