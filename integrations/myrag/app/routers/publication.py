"""Publication router — publish/unpublish collections to Open WebUI."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.collection import CollectionConfig, PublicationConfig
from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/collections", tags=["Publication"])


class PublishRequest(BaseModel):
    alias_enabled: bool = True
    alias_name: str = ""
    alias_description: str = ""
    alias_tags: list[str] = []
    tool_enabled: bool = False
    tool_target_models: list[str] = []
    tool_methods: list[str] = [
        "search_collection", "view_article", "explore_graph", "browse_collection"
    ]
    embed_enabled: bool = False
    embed_prefix: str = ""
    visibility: str = "all"
    visibility_group: str = ""
    visibility_users: list[str] = []
    published_by: str = ""


@router.get("/{name}/publication")
async def get_publication_status(name: str):
    """Get the publication status of a collection."""
    config = CollectionConfig.load(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")

    pub = config.get_publication()
    return pub.to_dict()


@router.post("/{name}/publish")
async def publish_collection(name: str, req: PublishRequest):
    """Publish a collection to Open WebUI.

    Creates/updates the model alias, tool attachment, and visibility settings.
    """
    config = CollectionConfig.load(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")

    pub = config.get_publication()

    # Update publication config
    pub.state = "published"
    pub.published_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    pub.published_by = req.published_by or "admin"

    pub.alias_enabled = req.alias_enabled
    pub.alias_name = req.alias_name or f"MyRAG {name}"
    pub.alias_description = req.alias_description or config.description
    pub.alias_tags = req.alias_tags or ["MyRAG", "RAG"]

    pub.tool_enabled = req.tool_enabled
    pub.tool_target_models = req.tool_target_models
    pub.tool_methods = req.tool_methods

    pub.embed_enabled = req.embed_enabled
    pub.embed_prefix = req.embed_prefix or f"#{name}"

    pub.visibility = req.visibility
    pub.visibility_group = req.visibility_group
    pub.visibility_users = req.visibility_users

    # Add to history
    pub.history.append({
        "action": "published",
        "at": pub.published_at,
        "by": pub.published_by,
        "modes": {
            "alias": pub.alias_enabled,
            "tool": pub.tool_enabled,
            "embed": pub.embed_enabled,
        },
        "visibility": pub.visibility,
    })

    config.set_publication(pub)
    config.save()

    # TODO: Actually push to OWUI via API/SQLite
    # For now, just update the config — OWUI integration will be done
    # when the OWUI API for model management is available

    return {
        "state": pub.state,
        "collection": name,
        "alias_name": pub.alias_name,
        "modes": {
            "alias": pub.alias_enabled,
            "tool": pub.tool_enabled,
            "embed": pub.embed_enabled,
        },
        "visibility": pub.visibility,
    }


@router.post("/{name}/unpublish")
async def unpublish_collection(name: str):
    """Disable a published collection (keeps data, hides from OWUI)."""
    config = CollectionConfig.load(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")

    pub = config.get_publication()
    pub.state = "disabled"
    pub.history.append({
        "action": "disabled",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "by": "admin",
    })

    config.set_publication(pub)
    config.save()

    return {"state": pub.state, "collection": name}


@router.post("/{name}/archive")
async def archive_collection(name: str):
    """Archive a collection (removes from OWUI, keeps data in MyRAG)."""
    config = CollectionConfig.load(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")

    pub = config.get_publication()
    pub.state = "archived"
    pub.history.append({
        "action": "archived",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "by": "admin",
    })

    config.set_publication(pub)
    config.save()

    return {"state": pub.state, "collection": name}


@router.get("/{name}/publication/history")
async def publication_history(name: str):
    """Get the publication history for a collection."""
    config = CollectionConfig.load(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")

    pub = config.get_publication()
    return {"collection": name, "history": pub.history}
