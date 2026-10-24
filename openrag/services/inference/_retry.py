import os
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from core.utils.exceptions import OpenRAGError
from core.utils.logging import get_logger
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    wait_exponential_jitter,
)

logger = get_logger()

_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
_RATE_LIMITED = 429


def _env_number(name: str, default: float, cast: type) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = cast(raw)
    except ValueError:
        logger.warning("Ignoring invalid {name}={raw!r}; using {default}", name=name, raw=raw, default=default)
        return default
    return value if value > 0 else default


# A 429 is a quota, not a fault: a per-minute gateway quota frees up within
# tens of seconds, so the 5xx budget (a few attempts, ~3-5 s in total) gives up
# long before the quota does. 429s get their own, longer budget. Keep the total
# below the deadlines that wrap these calls (contextualization_timeout, 120 s by
# default): the defaults spend at most ~2+4+8+16+32 s waiting.
RATE_LIMIT_MAX_ATTEMPTS = int(_env_number("INFERENCE_RATE_LIMIT_MAX_ATTEMPTS", 6, int))
RATE_LIMIT_MAX_WAIT = _env_number("INFERENCE_RATE_LIMIT_MAX_WAIT", 60.0, float)
_RATE_LIMIT_BASE_WAIT = 2.0


def _status_code(exc: BaseException) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    if isinstance(exc, OpenRAGError):
        return exc.status_code
    return None


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    return _status_code(exc) in _RETRYABLE_STATUS_CODES


def _is_rate_limited(exc: BaseException | None) -> bool:
    return exc is not None and _status_code(exc) == _RATE_LIMITED


def _http_response(exc: BaseException) -> httpx.Response | None:
    """The provider's response behind *exc*.

    The clients translate ``httpx.HTTPStatusError`` into an ``OpenRAGError``
    ``from exc``, so the response (and its headers) stays reachable on the cause
    chain without every error class having to copy it.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.HTTPStatusError):
            return current.response
        current = current.__cause__
    return None


def retry_after_seconds(exc: BaseException, *, now: datetime | None = None) -> float | None:
    """Seconds the provider asked us to wait (``Retry-After``), if it said so.

    Accepts both forms RFC 9110 allows: delta-seconds and an HTTP date.
    Returns ``None`` when the header is absent or unreadable.
    """
    response = _http_response(exc)
    if response is None:
        return None
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    raw = raw.strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


class _StopPolicy:
    """Stop after ``max_attempts``, or ``rate_limit_attempts`` while rate-limited."""

    def __init__(self, max_attempts: int, rate_limit_attempts: int):
        self.max_attempts = max_attempts
        self.rate_limit_attempts = rate_limit_attempts

    def limit_for(self, exc: BaseException | None) -> int:
        return self.rate_limit_attempts if _is_rate_limited(exc) else self.max_attempts

    def __call__(self, state: RetryCallState) -> bool:
        exc = state.outcome.exception() if state.outcome else None
        return state.attempt_number >= self.limit_for(exc)


class _WaitPolicy:
    """``Retry-After`` when given, else exponential backoff with jitter.

    429s back off from a longer base and up to a longer cap than other
    transient failures; both caps also bound a provider-supplied ``Retry-After``.
    """

    def __init__(self, base_wait: float, max_wait: float, rate_limit_max_wait: float):
        self._default = wait_exponential_jitter(initial=base_wait, max=max_wait, exp_base=2)
        self._rate_limited = wait_exponential_jitter(initial=_RATE_LIMIT_BASE_WAIT, max=rate_limit_max_wait, exp_base=2)
        self._rate_limit_max_wait = rate_limit_max_wait
        self._max_wait = max_wait

    def __call__(self, state: RetryCallState) -> float:
        exc = state.outcome.exception() if state.outcome else None
        rate_limited = _is_rate_limited(exc)
        if exc is not None:
            asked = retry_after_seconds(exc)
            if asked is not None:
                cap = self._rate_limit_max_wait if rate_limited else self._max_wait
                # A little jitter so callers told the same instant don't all return together.
                return min(asked, cap) + random.uniform(0, 1)
        return self._rate_limited(state) if rate_limited else self._default(state)


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    stop = state.retry_object.stop
    limit = stop.limit_for(exc) if isinstance(stop, _StopPolicy) else "?"
    logger.warning(
        "Retrying after transient failure (attempt {attempt}/{max}, waiting {wait:.1f}s): {exc}",
        attempt=state.attempt_number,
        max=limit,
        wait=state.upcoming_sleep,
        exc=repr(exc),
    )


def with_retry(
    max_attempts: int = 3,
    base_wait: float = 1.0,
    max_wait: float = 30.0,
    *,
    rate_limit_attempts: int | None = None,
    rate_limit_max_wait: float | None = None,
):
    """Retry transient inference failures (timeouts, connect errors, 429/502/503/504).

    ``max_attempts`` / ``base_wait`` / ``max_wait`` govern timeouts and 5xx.
    A 429 gets ``rate_limit_attempts`` (default ``INFERENCE_RATE_LIMIT_MAX_ATTEMPTS``,
    never fewer than ``max_attempts``) and waits up to ``rate_limit_max_wait``
    (default ``INFERENCE_RATE_LIMIT_MAX_WAIT``), honouring ``Retry-After``.
    """
    rl_attempts = max(max_attempts, rate_limit_attempts or RATE_LIMIT_MAX_ATTEMPTS)
    rl_max_wait = rate_limit_max_wait or RATE_LIMIT_MAX_WAIT
    return retry(
        stop=_StopPolicy(max_attempts, rl_attempts),
        wait=_WaitPolicy(base_wait, max_wait, rl_max_wait),
        retry=retry_if_exception(_is_retryable),
        before_sleep=_log_retry,
        reraise=True,
    )
