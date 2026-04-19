"""Tests for publication lifecycle (TDD)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.config
    monkeypatch.setattr(app.config.settings, "data_dir", str(tmp_path))
    from app.main import app
    return TestClient(app)


@pytest.fixture
def collection_with_config(tmp_path):
    """Create a collection config on disk."""
    import json
    col_dir = tmp_path / "test-col"
    col_dir.mkdir()
    config = {
        "name": "test-col",
        "description": "Test collection",
        "strategy": "article",
        "sensitivity": "public",
        "prompt_template": "generic",
        "system_prompt": "Tu es un assistant.",
        "graph_enabled": False,
        "ai_summary_enabled": False,
        "ai_summary_threshold": 1000,
        "scope": "group",
        "created_at": "2026-04-19T10:00:00",
        "publication": {
            "state": "draft",
            "alias_enabled": True,
            "alias_name": "MirAI Test",
            "tool_enabled": False,
            "embed_enabled": False,
            "visibility": "all",
        },
    }
    (col_dir / "metadata.json").write_text(json.dumps(config))


class TestPublicationConfig:
    def test_default_state_is_draft(self, client):
        from app.models.collection import PublicationConfig
        pub = PublicationConfig()
        assert pub.state == "draft"

    def test_publication_in_collection(self, client, collection_with_config):
        response = client.get("/api/collections/test-col")
        assert response.status_code == 200
        data = response.json()
        assert "publication" in data
        assert data["publication"]["state"] == "draft"


class TestPublicationEndpoints:
    def test_get_publication_status(self, client, collection_with_config):
        response = client.get("/api/collections/test-col/publication")
        assert response.status_code == 200
        assert response.json()["state"] == "draft"

    @patch("app.routers.publication.OpenRAGClient")
    def test_publish(self, mock_client_cls, client, collection_with_config):
        mock_client_cls.return_value.health_check = AsyncMock(return_value=True)
        response = client.post("/api/collections/test-col/publish", json={
            "alias_enabled": True,
            "alias_name": "MirAI Test Col",
            "tool_enabled": True,
            "visibility": "all",
        })
        assert response.status_code == 200
        assert response.json()["state"] == "published"

    def test_publish_nonexistent(self, client):
        response = client.post("/api/collections/nonexistent/publish", json={})
        assert response.status_code == 404

    @patch("app.routers.publication.OpenRAGClient")
    def test_unpublish(self, mock_client_cls, client, collection_with_config):
        # First publish
        mock_client_cls.return_value.health_check = AsyncMock(return_value=True)
        client.post("/api/collections/test-col/publish", json={"alias_enabled": True})
        # Then unpublish
        response = client.post("/api/collections/test-col/unpublish")
        assert response.status_code == 200
        assert response.json()["state"] == "disabled"

    @patch("app.routers.publication.OpenRAGClient")
    def test_archive(self, mock_client_cls, client, collection_with_config):
        mock_client_cls.return_value.health_check = AsyncMock(return_value=True)
        client.post("/api/collections/test-col/publish", json={"alias_enabled": True})
        response = client.post("/api/collections/test-col/archive")
        assert response.status_code == 200
        assert response.json()["state"] == "archived"

    def test_publication_history(self, client, collection_with_config):
        response = client.get("/api/collections/test-col/publication/history")
        assert response.status_code == 200
        assert "history" in response.json()
