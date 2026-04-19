"""Feedback CRUD service backed by SQLAlchemy database.

Replaces file-based FeedbackService.
"""

from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.db import Feedback


async def ingest_feedback(
    collection: str, question: str, response: str, rating: int,
    reason: str = "", owui_chat_id: str = "", owui_message_id: str = "",
) -> dict:
    """Ingest feedback. Idempotent on owui_message_id."""
    async with async_session() as session:
        # Deduplicate
        if owui_message_id:
            result = await session.execute(
                select(Feedback).where(Feedback.owui_message_id == owui_message_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.rating = rating
                existing.reason = reason
                await session.commit()
                await session.refresh(existing)
                return existing.to_dict()

        fb = Feedback(
            collection_name=collection,
            question=question,
            response=response,
            rating=rating,
            reason=reason,
            owui_chat_id=owui_chat_id,
            owui_message_id=owui_message_id,
        )
        session.add(fb)
        await session.commit()
        await session.refresh(fb)
        return fb.to_dict()


async def list_feedback(
    collection: str, status: str | None = None, rating: int | None = None,
) -> list[dict]:
    async with async_session() as session:
        query = select(Feedback).where(
            Feedback.collection_name == collection
        ).order_by(Feedback.created_at.desc())
        if status:
            query = query.where(Feedback.status == status)
        if rating is not None:
            query = query.where(Feedback.rating == rating)
        result = await session.execute(query)
        return [f.to_dict() for f in result.scalars().all()]


async def get_feedback(feedback_id: int) -> dict | None:
    async with async_session() as session:
        fb = await session.get(Feedback, feedback_id)
        return fb.to_dict() if fb else None


async def review_feedback(feedback_id: int, status: str = "reviewed", reviewed_by: str = "") -> dict | None:
    async with async_session() as session:
        fb = await session.get(Feedback, feedback_id)
        if not fb:
            return None
        fb.status = status
        fb.reviewed_by = reviewed_by
        fb.reviewed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(fb)
        return fb.to_dict()


async def promote_feedback(feedback_id: int, promote_to: str = "qr") -> dict | None:
    async with async_session() as session:
        fb = await session.get(Feedback, feedback_id)
        if not fb:
            return None
        fb.status = "promoted"
        fb.promoted_to = promote_to
        fb.reviewed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(fb)
        return fb.to_dict()


async def feedback_stats(collection: str) -> dict:
    async with async_session() as session:
        base = select(Feedback).where(Feedback.collection_name == collection)
        all_result = await session.execute(base)
        items = all_result.scalars().all()

        total = len(items)
        positive = sum(1 for f in items if f.rating > 0)
        negative = sum(1 for f in items if f.rating < 0)
        pending = sum(1 for f in items if f.status == "pending")

        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "satisfaction_rate": positive / total if total > 0 else 0,
            "pending_review": pending,
            "promoted": sum(1 for f in items if f.status == "promoted"),
        }
