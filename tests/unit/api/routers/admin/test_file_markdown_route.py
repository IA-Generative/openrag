"""``GET /partition/{partition}/file/{file_id}/markdown`` (mycollections#153)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from api.dependencies.auth import require_partition_viewer
from api.error_handlers import register_error_handlers
from api.routers.admin import partitions
from core.utils.exceptions import NotFoundError
from di.providers import get_partition_service
from fastapi import FastAPI
from services.orchestrators.partition_service import PartitionService

MARKDOWN = "<!-- page 1 -->\n# Circulaire\n\nTexte reconnu.\n"


class _FakeDocumentRepo:
    def __init__(self, metadata: dict | None) -> None:
        self.metadata = metadata

    async def get_file_metadata(self, file_id: str, partition: str) -> dict | None:
        return self.metadata


def _partition_service(data_dir, metadata: dict | None) -> PartitionService:
    return PartitionService(
        partition_repo=None,
        membership_repo=None,
        document_repo=_FakeDocumentRepo(metadata),
        vector_store=None,
        user_repo=None,
        collection="vdb_test",
        config=SimpleNamespace(paths=SimpleNamespace(data_dir=data_dir), partitions={}),
    )


def _app(service) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(partitions.router, prefix="/partition")
    app.dependency_overrides[get_partition_service] = lambda: service
    app.dependency_overrides[require_partition_viewer] = lambda: {"partition": "legal", "role": "viewer"}
    return app


def _upload_with_sidecar(tmp_path, text: str | None = MARKDOWN):
    upload = tmp_path / "legal" / "scan.pdf"
    upload.parent.mkdir()
    upload.write_bytes(b"%PDF")
    if text is not None:
        (tmp_path / "legal" / "scan.pdf.md").write_text(text, encoding="utf-8")
    return upload


@pytest.mark.asyncio
async def test_serves_the_markdown_copy_with_an_etag(tmp_path, async_client_factory):
    upload = _upload_with_sidecar(tmp_path)
    service = _partition_service(tmp_path, {"source": str(upload), "filename": "scan.pdf"})

    async with async_client_factory(_app(service)) as client:
        response = await client.get("/partition/legal/file/f1/markdown")
        cached = await client.get(
            "/partition/legal/file/f1/markdown", headers={"If-None-Match": response.headers["etag"]}
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.text == MARKDOWN
    assert response.headers["etag"].startswith('"') and response.headers["cache-control"] == "private, no-cache"
    assert cached.status_code == 304
    assert cached.content == b""


@pytest.mark.asyncio
async def test_a_changed_copy_gets_a_new_etag(tmp_path, async_client_factory):
    upload = _upload_with_sidecar(tmp_path)
    service = _partition_service(tmp_path, {"source": str(upload)})

    async with async_client_factory(_app(service)) as client:
        first = await client.get("/partition/legal/file/f1/markdown")
        (tmp_path / "legal" / "scan.pdf.md").write_text(MARKDOWN + "Page ajoutée.\n", encoding="utf-8")
        second = await client.get("/partition/legal/file/f1/markdown", headers={"If-None-Match": first.headers["etag"]})

    assert second.status_code == 200
    assert second.headers["etag"] != first.headers["etag"]


@pytest.mark.asyncio
async def test_a_file_without_copy_is_markdown_not_available(tmp_path, async_client_factory):
    upload = _upload_with_sidecar(tmp_path, text=None)
    service = _partition_service(tmp_path, {"source": str(upload)})

    async with async_client_factory(_app(service)) as client:
        response = await client.get("/partition/legal/file/f1/markdown")

    assert response.status_code == 404
    assert response.json()["detail"].startswith("[MARKDOWN_NOT_AVAILABLE]")
    assert "SAVE_MARKDOWN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_file_outside_the_partition_is_not_found(tmp_path, async_client_factory):
    _upload_with_sidecar(tmp_path)
    service = _partition_service(tmp_path, None)

    async with async_client_factory(_app(service)) as client:
        response = await client.get("/partition/legal/file/f1/markdown")

    assert response.status_code == 404
    assert response.json()["detail"].startswith("[FILE_NOT_FOUND]")


@pytest.mark.asyncio
async def test_a_source_outside_the_data_dir_is_never_read(tmp_path):
    outside = tmp_path / "elsewhere" / "secret.pdf"
    outside.parent.mkdir()
    (outside.parent / "secret.pdf.md").write_text("must not leak", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    service = _partition_service(data_dir, {"source": str(outside)})

    with pytest.raises(NotFoundError) as excinfo:
        await service.get_file_markdown(partition="legal", file_id="f1")

    assert excinfo.value.code == "MARKDOWN_NOT_AVAILABLE"
