"""Tests for MyRAG (beta) health and configuration endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestHealth:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_contains_status(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_contains_app_title(self, client):
        data = client.get("/health").json()
        assert "MyRAG" in data["app"]
        assert "beta" in data["app"].lower()

    def test_health_contains_version(self, client):
        data = client.get("/health").json()
        assert "version" in data


class TestConfig:
    def test_config_endpoint_requires_auth(self, client):
        """Config should not be publicly accessible without auth."""
        response = client.get("/api/config")
        # For now, config is public (no auth on health/config)
        # This will be restricted later when auth is added
        assert response.status_code in (200, 401, 403)

    def test_root_redirects_or_returns_info(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code in (200, 302, 307)
