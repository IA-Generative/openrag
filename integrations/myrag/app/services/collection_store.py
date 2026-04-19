"""Collection CRUD service backed by SQLAlchemy database."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.db import Collection


async def list_collections() -> list[dict]:
    async with async_session() as session:
        result = await session.execute(select(Collection).order_by(Collection.name))
        return [c.to_dict() for c in result.scalars().all()]


async def get_collection(name: str) -> dict | None:
    async with async_session() as session:
        c = await session.get(Collection, name)
        return c.to_dict() if c else None


async def create_collection(data: dict) -> dict:
    async with async_session() as session:
        c = Collection(**{k: v for k, v in data.items() if hasattr(Collection, k)})
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return c.to_dict()


async def update_collection(name: str, updates: dict) -> dict | None:
    allowed = {
        "description", "strategy", "sensitivity", "scope",
        "graph_enabled", "ai_summary_enabled", "ai_summary_threshold",
        "contact_name", "contact_email", "prompt_template",
        "system_prompt", "source_type", "source_url",
    }
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return None
        for key, value in updates.items():
            if key in allowed and hasattr(c, key):
                setattr(c, key, value)
        await session.commit()
        await session.refresh(c)
        return c.to_dict()


async def delete_collection(name: str) -> bool:
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return False
        await session.delete(c)
        await session.commit()
        return True


async def get_or_create_collection(name: str) -> dict:
    """Get a collection, creating a minimal one if it doesn't exist."""
    existing = await get_collection(name)
    if existing:
        return existing
    return await create_collection({"name": name})


async def get_system_prompt(name: str) -> str:
    async with async_session() as session:
        c = await session.get(Collection, name)
        return c.system_prompt if c else ""


async def update_system_prompt(name: str, prompt: str) -> dict | None:
    async with async_session() as session:
        c = await session.get(Collection, name)
        if not c:
            return None
        c.system_prompt = prompt
        await session.commit()
        await session.refresh(c)
        return c.to_dict()
