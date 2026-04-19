"""Feedback router — ingest, review, promote user feedback (DB-backed)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.feedback_store import (
    ingest_feedback as db_ingest,
    list_feedback as db_list,
    get_feedback as db_get,
    review_feedback as db_review,
    promote_feedback as db_promote,
    feedback_stats as db_stats,
)

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


class IngestRequest(BaseModel):
    collection: str
    question: str
    response: str
    rating: int
    reason: str = ""
    owui_chat_id: str = ""
    owui_message_id: str = ""


class ReviewRequest(BaseModel):
    status: str = "reviewed"
    reviewed_by: str = ""


class PromoteRequest(BaseModel):
    promote_to: str  # qr | eval
    corrected_answer: str = ""


@router.post("/ingest")
async def ingest_feedback_endpoint(req: IngestRequest):
    fb = await db_ingest(
        collection=req.collection,
        question=req.question,
        response=req.response,
        rating=req.rating,
        reason=req.reason,
        owui_chat_id=req.owui_chat_id,
        owui_message_id=req.owui_message_id,
    )
    return {"status": "ingested", "id": fb["id"]}


@router.get("/{collection}")
async def list_feedback_endpoint(
    collection: str,
    status: str | None = Query(None),
    rating: int | None = Query(None),
):
    items = await db_list(collection, status=status, rating=rating)
    return {"feedback": items}


@router.get("/{collection}/stats")
async def feedback_stats_endpoint(collection: str):
    return await db_stats(collection)


@router.patch("/{collection}/{feedback_id}/review")
async def review_feedback_endpoint(collection: str, feedback_id: int, req: ReviewRequest):
    result = await db_review(feedback_id, status=req.status, reviewed_by=req.reviewed_by)
    if not result:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"status": "updated"}


@router.post("/{collection}/{feedback_id}/promote")
async def promote_feedback_endpoint(collection: str, feedback_id: int, req: PromoteRequest):
    fb = await db_get(feedback_id)
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")

    await db_promote(feedback_id, promote_to=req.promote_to)

    if req.promote_to == "qr" and req.corrected_answer:
        from app.services.qr_cache import QRCache
        cache = QRCache()
        cache.add(collection, fb["question"], req.corrected_answer, source="feedback")

    return {"status": "promoted", "promote_to": req.promote_to}
