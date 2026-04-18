"""Tests for OpenRAG API client (TDD)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.openrag_client import OpenRAGClient


@pytest.fixture
def client():
    return OpenRAGClient(base_url="http://openrag:8080", admin_token="or-test-token")


class TestOpenRAGClient:
    def test_init(self, client):
        assert client.base_url == "http://openrag:8080"
        assert client.admin_token == "or-test-token"

    def test_headers(self, client):
        headers = client._headers()
        assert headers["Authorization"] == "Bearer or-test-token"
        assert "Content-Type" in headers

    @pytest.mark.asyncio
    async def test_create_partition(self, client):
        with patch.object(client, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status": "created"}
            result = await client.create_partition("test-collection")
            mock_post.assert_called_once()
            assert "partition/test-collection" in str(mock_post.call_args)

    @pytest.mark.asyncio
    async def test_upload_chunk(self, client):
        chunk = {
            "content": "Article L110-1 content",
            "filename": "Article-L110-1.md",
            "metadata": {"article": "L110-1"},
        }
        with patch.object(client, "_upload_file", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {"task_status_url": "/indexer/task/123"}
            result = await client.upload_chunk("test-collection", chunk)
            mock_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_search(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"documents": [{"content": "result"}]}
            result = await client.search("test-collection", "query", top_k=5)
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_models(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"data": [{"id": "openrag-test"}]}
            result = await client.list_models()
            assert len(result["data"]) == 1
