"""Tests for collection config and system prompt management."""

import json
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Patch settings.data_dir everywhere it's imported
    import app.config
    monkeypatch.setattr(app.config.settings, "data_dir", str(tmp_path))
    from app.main import app
    return TestClient(app)


@pytest.fixture
def sample_collection(tmp_path):
    """Create a sample collection config on disk."""
    col_dir = tmp_path / "test-col"
    col_dir.mkdir()
    config = {
        "name": "test-col",
        "description": "Test collection",
        "strategy": "article",
        "sensitivity": "public",
        "system_prompt": "Tu es un assistant test.",
        "graph_enabled": False,
        "scope": "group",
        "created_at": "2026-04-18T12:00:00",
    }
    (col_dir / "metadata.json").write_text(json.dumps(config))
    return config


class TestCollectionsCRUD:
    @patch("app.routers.collections.OpenRAGClient")
    def test_create_collection(self, mock_client_cls, client):
        mock_client = mock_client_cls.return_value
        mock_client.create_partition = AsyncMock(return_value={"status": "created"})

        response = client.post("/api/collections", json={
            "name": "my-col",
            "description": "Test",
            "strategy": "article",
            "sensitivity": "public",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["collection"]["name"] == "my-col"
        assert "system_prompt" in data["collection"]

    def test_list_collections_empty(self, client):
        response = client.get("/api/collections")
        assert response.status_code == 200
        assert response.json()["collections"] == []

    @patch("app.routers.collections.OpenRAGClient")
    def test_list_collections_with_data(self, mock_client_cls, client, sample_collection):
        mock_client_cls.return_value.create_partition = AsyncMock()
        response = client.get("/api/collections")
        assert response.status_code == 200
        cols = response.json()["collections"]
        assert len(cols) == 1
        assert cols[0]["name"] == "test-col"

    def test_get_collection(self, client, sample_collection):
        response = client.get("/api/collections/test-col")
        assert response.status_code == 200
        assert response.json()["name"] == "test-col"

    def test_get_collection_not_found(self, client):
        response = client.get("/api/collections/nonexistent")
        assert response.status_code == 404


class TestSystemPrompt:
    def test_get_system_prompt(self, client, sample_collection):
        response = client.get("/api/collections/test-col/system-prompt")
        assert response.status_code == 200
        assert response.json()["system_prompt"] == "Tu es un assistant test."
        assert response.json()["source"] == "collection"

    def test_get_system_prompt_default(self, client):
        response = client.get("/api/collections/unknown/system-prompt")
        assert response.status_code == 200
        assert response.json()["source"] == "default"
        assert "citer" in response.json()["system_prompt"].lower()

    def test_update_system_prompt(self, client, sample_collection):
        response = client.patch("/api/collections/test-col/system-prompt", json={
            "system_prompt": "Nouveau prompt juridique."
        })
        assert response.status_code == 200
        assert response.json()["system_prompt"] == "Nouveau prompt juridique."

        # Verify persistence
        response2 = client.get("/api/collections/test-col/system-prompt")
        assert response2.json()["system_prompt"] == "Nouveau prompt juridique."

    def test_update_system_prompt_not_found(self, client):
        response = client.patch("/api/collections/nonexistent/system-prompt", json={
            "system_prompt": "test"
        })
        assert response.status_code == 404
