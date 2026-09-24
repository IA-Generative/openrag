"""AuthMiddleware: anonymous ``/static/{extract_id}`` for public partitions only.

An unauthenticated ``GET /static/<id>`` reaches the download route only when the
resolver confirms the chunk belongs to a public partition; everything else keeps
the legacy responses (token mode 403 "Missing token", OIDC 302 to login / 401).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from api.middleware.auth import AuthMiddleware, resolve_public_download_partition
from fastapi import Request
from starlette.responses import Response


def _req(path: str, *, method: str = "GET", app=None) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("1.2.3.4", 1234),
    }
    if app is not None:
        scope["app"] = app
    return Request(scope)


def _anon_service() -> AsyncMock:
    svc = AsyncMock()
    svc.get_oidc_session_by_token_for_request = AsyncMock(return_value=None)
    svc.get_user_by_token_for_request = AsyncMock(return_value=None)
    return svc


class _Resolver:
    """Resolver double: ``{extract_id: public_partition}``; records calls."""

    def __init__(self, public: dict[str, str] | None = None, *, boom: bool = False):
        self.public = public or {}
        self.boom = boom
        self.calls: list[str] = []

    async def __call__(self, _request, extract_id: str):
        self.calls.append(extract_id)
        if self.boom:
            raise RuntimeError("vector store down")
        return self.public.get(extract_id)


def _middleware(resolver) -> AuthMiddleware:
    return AuthMiddleware(
        lambda scope, receive, send: None,
        get_auth_service=lambda _r: _anon_service(),
        resolve_public_download=resolver,
    )


async def _dispatch(mw, request):
    captured: dict = {}

    async def call_next(req):
        captured["user"] = req.state.user
        captured["user_partitions"] = req.state.user_partitions
        captured["public_partition"] = req.state.public_partition
        return Response("ok")

    return await mw.dispatch(request, call_next), captured


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")


@pytest.fixture(params=["oidc", "token"])
def auth_mode(request, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", request.param)
    monkeypatch.setenv("AUTH_TOKEN", "secret")
    monkeypatch.setenv("OIDC_TOKEN_ENCRYPTION_KEY", "x")
    return request.param


@pytest.mark.asyncio
async def test_anonymous_static_on_public_partition_is_forwarded(auth_mode):
    mw = _middleware(_Resolver({"123": "legal-public"}))

    resp, captured = await _dispatch(mw, _req("/static/123"))

    assert resp.status_code == 200
    assert captured == {"user": None, "user_partitions": [], "public_partition": "legal-public"}


@pytest.mark.asyncio
async def test_anonymous_static_on_private_partition_is_unchanged(auth_mode):
    mw = _middleware(_Resolver({}))

    resp, _ = await _dispatch(mw, _req("/static/123"))

    if auth_mode == "oidc":
        assert resp.status_code == 302
        assert resp.headers["location"] == "/auth/login?next=%2Fstatic%2F123"
    else:
        assert resp.status_code == 403
        assert resp.body == b'{"detail":"Missing token"}'


@pytest.mark.asyncio
async def test_public_check_fails_closed_on_resolver_error(auth_mode):
    mw = _middleware(_Resolver(boom=True))

    resp, _ = await _dispatch(mw, _req("/static/123"))

    assert resp.status_code == (302 if auth_mode == "oidc" else 403)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/static/123"),
        ("GET", "/static/123/extra"),
        ("GET", "/extract/123"),
        ("GET", "/search"),
        ("POST", "/v1/chat/completions"),
    ],
)
async def test_other_anonymous_routes_are_never_opened(auth_mode, method, path):
    resolver = _Resolver({"123": "legal-public"})
    mw = _middleware(resolver)

    resp, _ = await _dispatch(mw, _req(path, method=method))

    assert resp.status_code in (302, 401, 403)
    assert resolver.calls == []


def _app_with_container(*, chunk, public: set[str]):
    conversion = SimpleNamespace(get_chunk=AsyncMock(return_value=chunk))
    partitions = SimpleNamespace(is_partition_public=AsyncMock(side_effect=lambda name: name in public))
    return SimpleNamespace(
        state=SimpleNamespace(container=SimpleNamespace(conversion_service=conversion, partition_service=partitions))
    )


@pytest.mark.asyncio
async def test_default_resolver_returns_public_partition():
    app = _app_with_container(chunk={"metadata": {"partition": "legal-public"}}, public={"legal-public"})
    assert await resolve_public_download_partition(_req("/static/1", app=app), "1") == "legal-public"


@pytest.mark.asyncio
async def test_default_resolver_returns_none_for_private_partition():
    app = _app_with_container(chunk={"metadata": {"partition": "private"}}, public={"legal-public"})
    assert await resolve_public_download_partition(_req("/static/1", app=app), "1") is None


@pytest.mark.asyncio
async def test_default_resolver_returns_none_for_missing_chunk():
    app = _app_with_container(chunk=None, public={"legal-public"})
    assert await resolve_public_download_partition(_req("/static/1", app=app), "1") is None


@pytest.mark.asyncio
async def test_default_resolver_rejects_invalid_id_before_lookup():
    app = _app_with_container(chunk={"metadata": {"partition": "legal-public"}}, public={"legal-public"})
    with pytest.raises(Exception):
        await resolve_public_download_partition(_req("/static/x", app=app), "bad id")
    app.state.container.conversion_service.get_chunk.assert_not_awaited()
