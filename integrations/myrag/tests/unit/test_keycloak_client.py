"""Tests for Keycloak admin client (TDD)."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.keycloak_client import KeycloakClient


@pytest.fixture
def client():
    return KeycloakClient(
        base_url="http://keycloak:8080",
        realm="openwebui",
        client_id="myrag-admin",
        client_secret="test-secret",
        group_root="/myrag",
    )


class TestKeycloakClient:
    def test_init(self, client):
        assert client.realm == "openwebui"
        assert client.group_root == "/myrag"

    @pytest.mark.asyncio
    async def test_get_admin_token(self, client):
        with patch.object(client, "_post_form", new_callable=AsyncMock) as mock:
            mock.return_value = {"access_token": "tok123", "expires_in": 300}
            token = await client._get_admin_token()
            assert token == "tok123"

    @pytest.mark.asyncio
    async def test_create_group(self, client):
        with patch.object(client, "_admin_post", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            await client.create_group("ceseda-v3")
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_group_with_parent(self, client):
        with patch.object(client, "_admin_post", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            with patch.object(client, "_find_group_id", new_callable=AsyncMock) as mock_find:
                mock_find.return_value = "parent-uuid"
                await client.create_group("ceseda-v3", parent_id="parent-uuid")
                assert "children" in str(mock.call_args)

    @pytest.mark.asyncio
    async def test_list_group_members(self, client):
        with patch.object(client, "_admin_get", new_callable=AsyncMock) as mock:
            mock.return_value = [{"id": "user1", "username": "eric"}]
            members = await client.list_group_members("group-uuid")
            assert len(members) == 1

    @pytest.mark.asyncio
    async def test_add_user_to_group(self, client):
        with patch.object(client, "_admin_put", new_callable=AsyncMock) as mock:
            mock.return_value = {}
            await client.add_user_to_group("user-uuid", "group-uuid")
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_collection_groups(self, client):
        with patch.object(client, "create_group", new_callable=AsyncMock) as mock_create:
            with patch.object(client, "_find_group_id", new_callable=AsyncMock) as mock_find:
                mock_find.return_value = "myrag-root-uuid"
                mock_create.return_value = None
                await client.create_collection_groups("ceseda-v3")
                assert mock_create.call_count == 2  # collection + collection-admin
