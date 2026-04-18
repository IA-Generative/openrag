"""Feedback router — ingest, review, promote user feedback."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])

_svc = FeedbackService()


class IngestRequest(BaseModel):
    collection: str
    question: str
    response: str
    rating: int  # -1 or 1
    reason: str = ""
    user_id: str = ""
    owui_chat_id: str = ""
    owui_message_id: str = ""


class ReviewRequest(BaseModel):
    status: str = "reviewed"  # reviewed | ignored
    reviewed_by: str = ""


class PromoteRequest(BaseModel):
    promote_to: str  # qr | eval
    corrected_answer: str = ""  # for Q&R promotion


@router.post("/ingest")
async def ingest_feedback(req: IngestRequest):
    """Ingest feedback from OWUI (called by outlet function). Idempotent on owui_message_id."""
    fb = _svc.ingest(
        collection=req.collection,
        question=req.question,
        response=req.response,
        rating=req.rating,
        reason=req.reason,
        user_id=req.user_id,
        owui_chat_id=req.owui_chat_id,
        owui_message_id=req.owui_message_id,
    )
    return {"status": "ingested", "id": fb.id}


@router.get("/{collection}")
async def list_feedback(
    collection: str,
    status: str | None = Query(None),
    rating: int | None = Query(None),
):
    """List feedback for a collection, filterable by status and rating."""
    items = _svc.list(collection, status=status, rating=rating)
    return {"feedback": [f.to_dict() for f in items]}


@router.get("/{collection}/stats")
async def feedback_stats(collection: str):
    """Get feedback statistics for a collection."""
    return _svc.stats(collection)


@router.patch("/{collection}/{feedback_id}/review")
async def review_feedback(collection: str, feedback_id: str, req: ReviewRequest):
    """Review a feedback item (mark as reviewed or ignored)."""
    fb = _svc.get(collection, feedback_id)
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    _svc.review(feedback_id, collection, status=req.status, reviewed_by=req.reviewed_by)
    return {"status": "updated"}


@router.post("/{collection}/{feedback_id}/promote")
async def promote_feedback(collection: str, feedback_id: str, req: PromoteRequest):
    """Promote feedback to Q&R cache or eval dataset.

    - promote_to='qr': adds the question + corrected_answer to the Q&R cache
    - promote_to='eval': adds the question + corrected_answer to the eval dataset
    """
    fb = _svc.get(collection, feedback_id)
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")

    _svc.promote(feedback_id, collection, promote_to=req.promote_to)

    # If promoting to Q&R, actually add to the cache
    if req.promote_to == "qr" and req.corrected_answer:
        from app.services.qr_cache import QRCache
        cache = QRCache()
        cache.add(collection, fb.question, req.corrected_answer, source="feedback")

    # If promoting to eval, add to eval dataset
    if req.promote_to == "eval":
        from app.services.eval_service import EvalService
        eval_svc = EvalService()
        eval_svc.add_question(
            collection, fb.question,
            expected_answer=req.corrected_answer or fb.response,
            tags=["from-feedback"],
        )

    return {"status": "promoted", "promote_to": req.promote_to}
