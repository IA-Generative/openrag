"""Tests for sync service Keycloak ↔ OpenRAG (TDD)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.sync_service import SyncService


@pytest.fixture
def sync():
    return SyncService(
        keycloak_client=MagicMock(),
        openrag_client=MagicMock(),
    )


class TestSyncService:
    def test_init(self, sync):
        assert sync.kc is not None
        assert sync.openrag is not None

    def test_map_group_to_role_user(self, sync):
        assert sync._map_group_to_role("ceseda-v3") == "editor"

    def test_map_group_to_role_admin(self, sync):
        assert sync._map_group_to_role("ceseda-v3-admin") == "owner"

    def test_map_group_to_role_superadmin(self, sync):
        assert sync._map_group_to_role("superadmin") == "superadmin"

    @pytest.mark.asyncio
    async def test_sync_collection(self, sync):
        sync.kc.list_group_members = AsyncMock(return_value=[
            {"id": "kc-user-1", "username": "eric"},
            {"id": "kc-user-2", "username": "claire"},
        ])
        sync.openrag.create_partition = AsyncMock()
        sync.openrag._post = AsyncMock(return_value={"status": "ok"})
        sync.openrag._get = AsyncMock(return_value={"users": []})

        # Mock the upload form data for partition members
        sync.openrag._upload_form = AsyncMock(return_value={"status": "ok"})

        result = await sync.sync_collection(
            collection="ceseda-v3",
            user_group_id="ug-123",
            admin_group_id="ag-456",
        )
        assert result["collection"] == "ceseda-v3"
        assert result["synced"] >= 0

    @pytest.mark.asyncio
    async def test_sync_all(self, sync):
        sync.kc.list_collection_groups = AsyncMock(return_value=[
            {"collection": "ceseda-v3", "user_group_id": "ug-1", "admin_group_id": "ag-1"},
        ])
        sync.sync_collection = AsyncMock(return_value={"collection": "ceseda-v3", "synced": 2})

        results = await sync.sync_all()
        assert len(results) == 1
        assert results[0]["collection"] == "ceseda-v3"
