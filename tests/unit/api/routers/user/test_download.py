"""Tests for the authorized source-file download route under /static.

Covers the partition-membership check, DATA_DIR confinement, and the anonymous
public-partition path (``request.state.public_partition`` set by AuthMiddleware).
"""

from __future__ import annotations

from api.dependencies.auth import optional_user_partitions_list
from api.routers.user import download as download_module
from api.routers.user.download import router as download_router
from di.providers import get_conversion_service
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeConversionService:
    def __init__(self, chunk):
        self.chunk = chunk
        self.calls: list[str] = []

    async def get_chunk(self, chunk_id):
        self.calls.append(chunk_id)
        return self.chunk


def _client(chunk, partitions):
    app = FastAPI()
    app.include_router(download_router)
    app.dependency_overrides[optional_user_partitions_list] = lambda: partitions

    app.dependency_overrides[get_conversion_service] = lambda: _FakeConversionService(chunk)
    return TestClient(app)


def _client_with_service(chunk, partitions):
    app = FastAPI()
    service = _FakeConversionService(chunk)
    app.include_router(download_router)
    app.dependency_overrides[optional_user_partitions_list] = lambda: partitions
    app.dependency_overrides[get_conversion_service] = lambda: service
    return TestClient(app), service


def test_download_404_when_chunk_missing():
    client = _client(None, ["p1"])
    assert client.get("/static/123").status_code == 404


def test_download_403_when_user_lacks_partition_access():
    chunk = {"metadata": {"partition": "other-tenant", "source": "/data/secret.pdf"}}
    client = _client(chunk, ["p1"])
    r = client.get("/static/123")
    assert r.status_code == 403


def test_download_404_when_source_path_escapes_data_dir():
    # Partition access is granted, but the source path resolves outside DATA_DIR
    # (path-traversal attempt) → 404, never served.
    chunk = {"metadata": {"partition": "p1", "source": "/etc/passwd"}}
    client = _client(chunk, ["p1"])
    assert client.get("/static/123").status_code == 404


def test_download_404_when_source_missing():
    chunk = {"metadata": {"partition": "p1"}}
    client = _client(chunk, ["p1"])
    assert client.get("/static/123").status_code == 404


def test_download_rejects_invalid_extract_id_before_storage_lookup():
    client, service = _client_with_service(None, ["p1"])

    response = client.get("/static/bad%20id")

    assert response.status_code == 400
    assert service.calls == []


def _anonymous_client(chunk, public_partition):
    """App where the request is anonymous, as AuthMiddleware forwards a public download."""
    app = FastAPI()

    @app.middleware("http")
    async def _anonymous(request, call_next):
        request.state.user = None
        request.state.user_partitions = []
        if public_partition is not None:
            request.state.public_partition = public_partition
        return await call_next(request)

    app.include_router(download_router)
    app.dependency_overrides[get_conversion_service] = lambda: _FakeConversionService(chunk)
    return TestClient(app)


def test_anonymous_download_of_public_partition_file_is_served(tmp_path, monkeypatch):
    monkeypatch.setattr(download_module, "_DATA_DIR", tmp_path.resolve())
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4 public")
    chunk = {"metadata": {"partition": "public-p", "source": str(source)}}

    r = _anonymous_client(chunk, "public-p").get("/static/123")

    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 public"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_anonymous_download_refused_when_chunk_is_in_another_partition(tmp_path, monkeypatch):
    # public_partition vetted by the middleware must match the chunk's partition.
    monkeypatch.setattr(download_module, "_DATA_DIR", tmp_path.resolve())
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4")
    chunk = {"metadata": {"partition": "private-p", "source": str(source)}}

    assert _anonymous_client(chunk, "public-p").get("/static/123").status_code == 403


def test_anonymous_download_refused_without_middleware_vetting(tmp_path, monkeypatch):
    monkeypatch.setattr(download_module, "_DATA_DIR", tmp_path.resolve())
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4")
    chunk = {"metadata": {"partition": "public-p", "source": str(source)}}

    assert _anonymous_client(chunk, None).get("/static/123").status_code == 403


def test_anonymous_public_download_keeps_data_dir_confinement(tmp_path, monkeypatch):
    monkeypatch.setattr(download_module, "_DATA_DIR", tmp_path.resolve())
    chunk = {"metadata": {"partition": "public-p", "source": "/etc/passwd"}}

    assert _anonymous_client(chunk, "public-p").get("/static/123").status_code == 404
