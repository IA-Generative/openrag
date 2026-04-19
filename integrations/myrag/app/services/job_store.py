"""IngestJob CRUD service backed by SQLAlchemy database.

Replaces the in-memory job_tracker.py.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.db import IngestJob


async def create_job(
    collection: str, filename: str, strategy: str, sensitivity: str,
    source_path: str = "",
) -> dict:
    job = IngestJob(
        job_id=str(uuid.uuid4())[:8],
        collection_name=collection,
        filename=filename,
        source_path=source_path,
        strategy=strategy,
        sensitivity=sensitivity,
        status="chunking",
    )
    async with async_session() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.to_dict()


async def get_job(job_id: str) -> dict | None:
    async with async_session() as session:
        job = await session.get(IngestJob, job_id)
        return job.to_dict() if job else None


async def update_job(job_id: str, **kwargs) -> dict | None:
    async with async_session() as session:
        job = await session.get(IngestJob, job_id)
        if not job:
            return None
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        await session.commit()
        await session.refresh(job)
        return job.to_dict()


async def increment_job_progress(job_id: str, success: bool = True):
    """Increment uploaded_chunks (and failed_chunks if not success)."""
    async with async_session() as session:
        job = await session.get(IngestJob, job_id)
        if not job:
            return
        job.uploaded_chunks += 1
        if not success:
            job.failed_chunks += 1
        await session.commit()


async def complete_job(job_id: str):
    """Mark job as done or done_with_errors."""
    async with async_session() as session:
        job = await session.get(IngestJob, job_id)
        if not job:
            return
        job.status = "done" if job.failed_chunks == 0 else "done_with_errors"
        job.completed_at = datetime.now(timezone.utc)
        await session.commit()


async def list_jobs(collection: str | None = None) -> list[dict]:
    async with async_session() as session:
        query = select(IngestJob).order_by(IngestJob.created_at.desc())
        if collection:
            query = query.where(IngestJob.collection_name == collection)
        result = await session.execute(query)
        return [j.to_dict() for j in result.scalars().all()]
