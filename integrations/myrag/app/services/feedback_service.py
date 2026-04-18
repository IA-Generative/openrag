"""Feedback Service — collect and manage user feedback from OWUI."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Feedback:
    id: str
    collection: str
    question: str
    response: str
    rating: int  # -1 (negative) or 1 (positive)
    reason: str = ""
    user_id: str = ""
    owui_chat_id: str = ""
    owui_message_id: str = ""
    status: str = "pending"  # pending | reviewed | promoted | ignored
    promoted_to: str = ""  # qr | eval | ""
    reviewed_by: str = ""
    created_at: float = field(default_factory=time.time)
    reviewed_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class FeedbackService:
    """Per-collection feedback management with persistence."""

    def __init__(self, data_dir: str | None = None):
        from app.config import settings
        self.data_dir = data_dir or settings.data_dir

    def _path(self, collection: str) -> Path:
        return Path(self.data_dir) / collection / "feedback.json"

    def _load(self, collection: str) -> list[Feedback]:
        path = self._path(collection)
        if not path.exists():
            return []
        return [Feedback(**f) for f in json.loads(path.read_text())]

    def _save(self, collection: str, items: list[Feedback]):
        path = self._path(collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([f.to_dict() for f in items], indent=2, ensure_ascii=False))

    def ingest(self, collection: str, question: str, response: str,
               rating: int, reason: str = "", user_id: str = "",
               owui_chat_id: str = "", owui_message_id: str = ""):
        """Ingest a feedback item. Idempotent on owui_message_id."""
        items = self._load(collection)

        # Deduplicate by owui_message_id
        if owui_message_id:
            for item in items:
                if item.owui_message_id == owui_message_id:
                    item.rating = rating
                    item.reason = reason
                    self._save(collection, items)
                    return item

        fb = Feedback(
            id=str(uuid.uuid4())[:8],
            collection=collection,
            question=question,
            response=response,
            rating=rating,
            reason=reason,
            user_id=user_id,
            owui_chat_id=owui_chat_id,
            owui_message_id=owui_message_id,
        )
        items.append(fb)
        self._save(collection, items)
        return fb

    def list(self, collection: str, status: str | None = None,
             rating: int | None = None) -> list[Feedback]:
        items = self._load(collection)
        if status:
            items = [f for f in items if f.status == status]
        if rating is not None:
            items = [f for f in items if f.rating == rating]
        return items

    def get(self, collection: str, feedback_id: str) -> Feedback | None:
        for f in self._load(collection):
            if f.id == feedback_id:
                return f
        return None

    def review(self, feedback_id: str, collection: str,
               status: str = "reviewed", reviewed_by: str = ""):
        items = self._load(collection)
        for f in items:
            if f.id == feedback_id:
                f.status = status
                f.reviewed_by = reviewed_by
                f.reviewed_at = time.time()
                break
        self._save(collection, items)

    def promote(self, feedback_id: str, collection: str,
                promote_to: str = "qr"):
        """Promote a feedback to Q&R cache or eval dataset."""
        items = self._load(collection)
        for f in items:
            if f.id == feedback_id:
                f.status = "promoted"
                f.promoted_to = promote_to
                f.reviewed_at = time.time()
                break
        self._save(collection, items)

    def stats(self, collection: str) -> dict:
        items = self._load(collection)
        positive = sum(1 for f in items if f.rating > 0)
        negative = sum(1 for f in items if f.rating < 0)
        total = len(items)
        pending = sum(1 for f in items if f.status == "pending")

        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "satisfaction_rate": positive / total if total > 0 else 0,
            "pending_review": pending,
            "promoted": sum(1 for f in items if f.status == "promoted"),
        }
