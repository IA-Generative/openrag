"""Workspace management endpoints."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from utils.dependencies import get_vectordb
from utils.logger import get_logger

from .utils import require_partition_editor, require_partition_owner, require_partition_viewer

router = APIRouter()
logger = get_logger()


class CreateWorkspaceRequest(BaseModel):
    workspace_id: str
    display_name: str | None = None


class AddFilesRequest(BaseModel):
    file_ids: list[str]


async def require_workspace_in_partition(partition: str, workspace_id: str, vectordb=Depends(get_vectordb)) -> dict:
    """Validate that a workspace exists and belongs to the given partition."""
    ws = await vectordb.get_workspace.remote(workspace_id)
    if not ws or ws["partition_name"] != partition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


@router.post(
    "/partition/{partition}/workspaces",
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace(
    partition: str,
    body: CreateWorkspaceRequest,
    user=Depends(require_partition_editor),
    vectordb=Depends(get_vectordb),
):
    existing = await vectordb.get_workspace.remote(body.workspace_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workspace '{body.workspace_id}' already exists.",
        )
    await vectordb.create_workspace.remote(
        workspace_id=body.workspace_id,
        partition=partition,
        user_id=user["id"],
        display_name=body.display_name,
    )
    return {"status": "created", "workspace_id": body.workspace_id}


@router.get(
    "/partition/{partition}/workspaces",
    dependencies=[Depends(require_partition_viewer)],
)
async def list_workspaces(partition: str, vectordb=Depends(get_vectordb)):
    workspaces = await vectordb.list_workspaces.remote(partition)
    return {"workspaces": workspaces}


@router.get(
    "/partition/{partition}/workspaces/{workspace_id}",
    dependencies=[Depends(require_partition_viewer)],
)
async def get_workspace(ws=Depends(require_workspace_in_partition)):
    return ws


@router.delete(
    "/partition/{partition}/workspaces/{workspace_id}",
    dependencies=[Depends(require_partition_owner)],
)
async def delete_workspace(
    partition: str, workspace_id: str, vectordb=Depends(get_vectordb), _ws=Depends(require_workspace_in_partition)
):
    orphaned = await vectordb.delete_workspace.remote(workspace_id)
    if orphaned:
        results = await asyncio.gather(
            *[vectordb.delete_file.remote(file_id, partition) for file_id in orphaned],
            return_exceptions=True,
        )
        for file_id, result in zip(orphaned, results):
            if isinstance(result, Exception):
                logger.warning("Failed to delete orphaned file from Milvus", file_id=file_id, error=str(result))
    return {"status": "deleted", "orphaned_files_deleted": len(orphaned)}


@router.post(
    "/partition/{partition}/workspaces/{workspace_id}/files",
    dependencies=[Depends(require_partition_editor)],
)
async def add_files_to_workspace(
    workspace_id: str,
    body: AddFilesRequest,
    vectordb=Depends(get_vectordb),
    _ws=Depends(require_workspace_in_partition),
):
    await vectordb.add_files_to_workspace.remote(workspace_id, body.file_ids)
    return {"status": "added", "file_ids": body.file_ids}


@router.get(
    "/partition/{partition}/workspaces/{workspace_id}/files",
    dependencies=[Depends(require_partition_viewer)],
)
async def list_workspace_files(
    workspace_id: str, vectordb=Depends(get_vectordb), _ws=Depends(require_workspace_in_partition)
):
    file_ids = await vectordb.list_workspace_files.remote(workspace_id)
    return {"file_ids": file_ids}


@router.delete(
    "/partition/{partition}/workspaces/{workspace_id}/files/{file_id}",
    dependencies=[Depends(require_partition_editor)],
)
async def remove_file_from_workspace(
    workspace_id: str, file_id: str, vectordb=Depends(get_vectordb), _ws=Depends(require_workspace_in_partition)
):
    removed = await vectordb.remove_file_from_workspace.remote(workspace_id, file_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in workspace")
    return {"status": "removed"}
