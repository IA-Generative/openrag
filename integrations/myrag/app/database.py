"""Database engine and session management for MyRAG.

Supports SQLite (dev) and PostgreSQL (prod) via DATABASE_URL:
  - sqlite+aiosqlite:///app/data/myrag.db  (default)
  - postgresql+asyncpg://user:pass@host:5432/myrag
"""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Ensure the data directory exists for SQLite
if "sqlite" in settings.database_url:
    db_path = settings.database_url.split("///")[-1]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # SQLite needs this for concurrent access
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables. Called on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get a database session (for use with FastAPI Depends)."""
    async with async_session() as session:
        yield session
