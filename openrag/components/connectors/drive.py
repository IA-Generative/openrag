"""Drive connector for Suite Numérique Drive integration.

Provides:
- DriveClient: HTTP client for the Drive REST API
- DriveConnector: Sync logic (new/modified/deleted files)
- DriveSyncScheduler: Ray actor for periodic sync
"""

import asyncio
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime

import httpx
import ray
from config import load_config
from utils.logger import get_logger

logger = get_logger()
config = load_config()

DRIVE_DEFAULT_BASE_URL = os.getenv("DRIVE_DEFAULT_BASE_URL", "")
DRIVE_SERVICE_ACCOUNT_CLIENT_ID = os.getenv("DRIVE_SERVICE_ACCOUNT_CLIENT_ID", "")
DRIVE_SERVICE_ACCOUNT_CLIENT_SECRET = os.getenv("DRIVE_SERVICE_ACCOUNT_CLIENT_SECRET", "")
OIDC_ISSUER_URL = os.getenv("OIDC_ISSUER_URL", "")


@dataclass
class DriveItem:
    id: str
    type: str  # "FILE" or "FOLDER"
    title: str
    updated_at: str | None = None


class DriveClient:
    """HTTP client for the Suite Numérique Drive API."""

    def __init__(self, base_url: str, access_token: str):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v1.0",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )

    async def list_folder(self, folder_id: str, recursive: bool = True) -> list[DriveItem]:
        """List all files in a folder, optionally recursively."""
        items = []
        page = 1
        while True:
            resp = await self._client.get(f"/items/{folder_id}/children/", params={"page": page})
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", data) if isinstance(data, dict) else data
            if not results:
                break

            for item_data in results:
                item = DriveItem(
                    id=item_data["id"],
                    type=item_data.get("type", "FILE"),
                    title=item_data.get("title", ""),
                    updated_at=item_data.get("updated_at"),
                )
                if item.type == "FILE":
                    items.append(item)
                elif item.type == "FOLDER" and recursive:
                    sub_items = await self.list_folder(item.id, recursive=True)
                    items.extend(sub_items)

            # Check for pagination
            next_url = data.get("next") if isinstance(data, dict) else None
            if not next_url:
                break
            page += 1

        return items

    async def download_file(self, item_id: str) -> tuple[bytes, str]:
        """Download a file and return (content_bytes, filename)."""
        resp = await self._client.get(f"/items/{item_id}/download/")
        resp.raise_for_status()

        # Extract filename from Content-Disposition header
        cd = resp.headers.get("content-disposition", "")
        filename = ""
        if "filename=" in cd:
            filename = cd.split("filename=")[1].strip('"').strip("'")
        if not filename:
            filename = f"drive_{item_id}"

        return resp.content, filename

    async def get_item(self, item_id: str) -> DriveItem:
        """Get metadata for a single item."""
        resp = await self._client.get(f"/items/{item_id}/")
        resp.raise_for_status()
        data = resp.json()
        return DriveItem(
            id=data["id"],
            type=data.get("type", "FILE"),
            title=data.get("title", ""),
            updated_at=data.get("updated_at"),
        )

    async def close(self):
        await self._client.aclose()


class DriveConnector:
    """Synchronizes a Drive folder with an OpenRAG partition."""

    async def get_access_token(self, source) -> str:
        """Obtain an OIDC access token for the Drive API.

        Uses client_credentials grant for service account auth.
        """
        client_id = source.service_account_client_id or DRIVE_SERVICE_ACCOUNT_CLIENT_ID
        client_secret = source.service_account_client_secret or DRIVE_SERVICE_ACCOUNT_CLIENT_SECRET
        issuer = OIDC_ISSUER_URL

        if not all([client_id, client_secret, issuer]):
            raise ValueError("Missing OIDC credentials for Drive service account")

        token_url = f"{issuer.rstrip('/')}/protocol/openid-connect/token"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def sync_source(self, source, session_factory) -> dict:
        """Synchronize a Drive source with its OpenRAG partition.

        Returns: {"added": int, "updated": int, "deleted": int, "errors": int}
        """
        from components.indexer.vectordb.utils import DriveFileMapping

        log = logger.bind(source_id=source.id, partition=source.partition_name)
        result = {"added": 0, "updated": 0, "deleted": 0, "errors": 0}

        try:
            token = await self.get_access_token(source)
            drive_client = DriveClient(source.drive_base_url, token)

            # List current files in Drive
            drive_items = await drive_client.list_folder(source.drive_folder_id)
            drive_items_by_id = {item.id: item for item in drive_items}

            # Load existing mappings
            with session_factory() as s:
                existing_mappings = (
                    s.query(DriveFileMapping)
                    .filter_by(drive_source_id=source.id)
                    .all()
                )
                existing_by_drive_id = {m.drive_item_id: m for m in existing_mappings}

            # Determine actions
            drive_ids = set(drive_items_by_id.keys())
            mapped_ids = set(existing_by_drive_id.keys())

            new_ids = drive_ids - mapped_ids
            deleted_ids = mapped_ids - drive_ids
            common_ids = drive_ids & mapped_ids

            # Check for updates (modified files)
            updated_ids = set()
            for item_id in common_ids:
                item = drive_items_by_id[item_id]
                mapping = existing_by_drive_id[item_id]
                if item.updated_at and mapping.drive_item_updated_at:
                    item_dt = datetime.fromisoformat(item.updated_at.replace("Z", "+00:00"))
                    if item_dt > mapping.drive_item_updated_at:
                        updated_ids.add(item_id)

            indexer = ray.get_actor("Indexer", namespace="openrag")
            vectordb = ray.get_actor("Vectordb", namespace="openrag")

            # Process new files
            for item_id in new_ids:
                item = drive_items_by_id[item_id]
                try:
                    content, filename = await drive_client.download_file(item_id)
                    file_id = f"drive_{source.id}_{item_id}"

                    # Save to temp file for indexer
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name

                    metadata = {
                        "file_id": file_id,
                        "source": filename,
                        "drive_source_id": source.id,
                        "drive_item_id": item_id,
                        "drive_url": f"{source.drive_base_url}/items/{item_id}",
                    }

                    await indexer.add_file.remote(
                        path=tmp_path,
                        metadata=metadata,
                        partition=source.partition_name,
                    )

                    # Record mapping
                    with session_factory() as s:
                        s.add(DriveFileMapping(
                            drive_source_id=source.id,
                            drive_item_id=item_id,
                            drive_item_title=item.title,
                            drive_item_updated_at=datetime.fromisoformat(item.updated_at.replace("Z", "+00:00")) if item.updated_at else None,
                            file_id=file_id,
                            partition_name=source.partition_name,
                        ))
                        s.commit()

                    result["added"] += 1
                    log.info("Added file from Drive", drive_item=item.title)

                except Exception as e:
                    log.warning("Failed to add Drive file", drive_item_id=item_id, error=str(e))
                    result["errors"] += 1

            # Process deleted files
            for item_id in deleted_ids:
                mapping = existing_by_drive_id[item_id]
                try:
                    await vectordb.delete_file.remote(mapping.file_id, source.partition_name)
                    with session_factory() as s:
                        m = s.query(DriveFileMapping).filter_by(id=mapping.id).first()
                        if m:
                            s.delete(m)
                            s.commit()
                    result["deleted"] += 1
                    log.info("Deleted file removed from Drive", file_id=mapping.file_id)
                except Exception as e:
                    log.warning("Failed to delete file", file_id=mapping.file_id, error=str(e))
                    result["errors"] += 1

            # Process updated files (delete + re-add)
            for item_id in updated_ids:
                mapping = existing_by_drive_id[item_id]
                item = drive_items_by_id[item_id]
                try:
                    # Delete old
                    await vectordb.delete_file.remote(mapping.file_id, source.partition_name)

                    # Re-download and re-index
                    content, filename = await drive_client.download_file(item_id)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name

                    metadata = {
                        "file_id": mapping.file_id,
                        "source": filename,
                        "drive_source_id": source.id,
                        "drive_item_id": item_id,
                        "drive_url": f"{source.drive_base_url}/items/{item_id}",
                    }

                    await indexer.add_file.remote(
                        path=tmp_path,
                        metadata=metadata,
                        partition=source.partition_name,
                    )

                    # Update mapping
                    with session_factory() as s:
                        m = s.query(DriveFileMapping).filter_by(id=mapping.id).first()
                        if m:
                            m.drive_item_updated_at = datetime.fromisoformat(item.updated_at.replace("Z", "+00:00")) if item.updated_at else None
                            m.last_synced_at = datetime.now()
                            s.commit()

                    result["updated"] += 1
                    log.info("Updated file from Drive", drive_item=item.title)

                except Exception as e:
                    log.warning("Failed to update Drive file", drive_item_id=item_id, error=str(e))
                    result["errors"] += 1

            await drive_client.close()

            # Update source status
            with session_factory() as s:
                from components.indexer.vectordb.utils import DriveSource as DS

                src = s.query(DS).filter_by(id=source.id).first()
                if src:
                    src.last_synced_at = datetime.now()
                    src.last_sync_status = "success"
                    src.last_sync_error = None
                    s.commit()

        except Exception as e:
            log.error("Drive sync failed", error=str(e))
            with session_factory() as s:
                from components.indexer.vectordb.utils import DriveSource as DS

                src = s.query(DS).filter_by(id=source.id).first()
                if src:
                    src.last_synced_at = datetime.now()
                    src.last_sync_status = "failed"
                    src.last_sync_error = str(e)
                    s.commit()

        return result


@ray.remote
class DriveSyncScheduler:
    """Ray actor that periodically syncs Drive sources."""

    def __init__(self):
        self.logger = get_logger()
        self.connector = DriveConnector()
        self._running = True

    async def run(self):
        """Main loop: check for sources that need syncing."""
        self.logger.info("DriveSyncScheduler started")
        while self._running:
            try:
                await self._check_and_sync()
            except Exception as e:
                self.logger.error("DriveSyncScheduler error", error=str(e))
            await asyncio.sleep(60)  # Check every minute

    async def _check_and_sync(self):
        from components.indexer.vectordb.utils import DriveSource
        from utils.dependencies import get_vectordb

        vectordb = get_vectordb()
        pfm = await vectordb.get_partition_file_manager.remote()

        with pfm.Session() as s:
            sources = s.query(DriveSource).filter_by(sync_enabled=True).all()
            sources_to_sync = []
            now = datetime.now()
            for src in sources:
                if src.last_synced_at is None:
                    sources_to_sync.append(src.id)
                else:
                    from datetime import timedelta

                    next_sync = src.last_synced_at + timedelta(minutes=src.sync_frequency_minutes)
                    if now >= next_sync:
                        sources_to_sync.append(src.id)

        for source_id in sources_to_sync:
            await self.trigger_sync(source_id)

    async def trigger_sync(self, source_id: int):
        """Trigger sync for a specific source."""
        from components.indexer.vectordb.utils import DriveSource
        from utils.dependencies import get_vectordb

        vectordb = get_vectordb()
        pfm = await vectordb.get_partition_file_manager.remote()

        with pfm.Session() as s:
            source = s.query(DriveSource).filter_by(id=source_id).first()
            if not source:
                self.logger.warning("Drive source not found", source_id=source_id)
                return

        self.logger.info("Starting Drive sync", source_id=source_id)
        result = await self.connector.sync_source(source, pfm.Session)
        self.logger.info("Drive sync completed", source_id=source_id, result=result)

    async def stop(self):
        self._running = False
