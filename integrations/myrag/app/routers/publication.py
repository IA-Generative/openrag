"""Publication router — publish/unpublish collections to Open WebUI."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import async_session
from app.models.db import Publication, PublicationHistory
from app.services.collection_store import get_or_create_collection

router = APIRouter(prefix="/api/collections", tags=["Publication"])


class PublishRequest(BaseModel):
    alias_enabled: bool = True
    alias_name: str = ""
    tool_enabled: bool = False
    embed_enabled: bool = False
    visibility: str = "all"
    visibility_groups: list[str] = []
    widget_enabled: bool = False
    browser_enabled: bool = False
    published_by: str = ""
    state: str = ""  # allow "draft" for save-as-draft


@router.get("/{name}/publication")
async def get_publication_status(name: str):
    async with async_session() as session:
        pub = await session.get(Publication, name)
        if not pub:
            return {"collection": name, "state": "draft"}
        return pub.to_dict()


@router.post("/{name}/publish")
async def publish_collection(name: str, req: PublishRequest):
    # Auto-create collection config if it doesn't exist
    await get_or_create_collection(name)

    now = datetime.now(timezone.utc)

    async with async_session() as session:
        pub = await session.get(Publication, name)
        if not pub:
            pub = Publication(collection_name=name)
            session.add(pub)

        pub.state = req.state if req.state == "draft" else "published"
        pub.alias_enabled = req.alias_enabled
        pub.alias_name = req.alias_name or f"📚 {name}"
        pub.tool_enabled = req.tool_enabled
        pub.embed_enabled = req.embed_enabled
        pub.visibility = req.visibility
        pub.visibility_groups_json = json.dumps(req.visibility_groups)
        pub.widget_enabled = req.widget_enabled
        pub.browser_enabled = req.browser_enabled
        pub.published_at = now
        pub.published_by = req.published_by or "admin"

        # History entry
        history = PublicationHistory(
            collection_name=name,
            action=pub.state,
            acted_by=pub.published_by,
            acted_at=now,
            details_json=json.dumps({
                "alias": pub.alias_enabled,
                "tool": pub.tool_enabled,
                "embed": pub.embed_enabled,
                "visibility": pub.visibility,
            }),
        )
        session.add(history)

        await session.commit()
        await session.refresh(pub)
        return pub.to_dict()


@router.post("/{name}/unpublish")
async def unpublish_collection(name: str):
    async with async_session() as session:
        pub = await session.get(Publication, name)
        if not pub:
            raise HTTPException(status_code=404, detail=f"No publication for '{name}'")
        pub.state = "disabled"

        session.add(PublicationHistory(
            collection_name=name, action="disabled", acted_by="admin",
        ))
        await session.commit()
        return {"state": pub.state, "collection": name}


@router.post("/{name}/archive")
async def archive_collection(name: str):
    async with async_session() as session:
        pub = await session.get(Publication, name)
        if not pub:
            raise HTTPException(status_code=404, detail=f"No publication for '{name}'")
        pub.state = "archived"

        session.add(PublicationHistory(
            collection_name=name, action="archived", acted_by="admin",
        ))
        await session.commit()
        return {"state": pub.state, "collection": name}


@router.get("/{name}/publication/history")
async def publication_history(name: str):
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(PublicationHistory)
            .where(PublicationHistory.collection_name == name)
            .order_by(PublicationHistory.acted_at.desc())
        )
        entries = result.scalars().all()
        return {
            "collection": name,
            "history": [
                {"action": h.action, "at": h.acted_at.isoformat(), "by": h.acted_by,
                 "details": json.loads(h.details_json or "{}")}
                for h in entries
            ],
        }
