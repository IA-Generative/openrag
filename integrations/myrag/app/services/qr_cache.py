"""Q&R Cache — semantic cache for frequent questions with curated answers."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path


@dataclass
class QREntry:
    id: str
    question: str
    answer: str
    tags: list[str] = field(default_factory=list)
    source: str = "manual"  # manual | feedback | import
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class QRCache:
    """Per-collection Q&R cache with persistence and simple text matching."""

    def __init__(self, data_dir: str | None = None):
        from app.config import settings
        self.data_dir = data_dir or settings.data_dir
        self._stats: dict[str, dict] = {}  # collection → {hits, misses}

    def _path(self, collection: str) -> Path:
        return Path(self.data_dir) / collection / "qr_cache.json"

    def _load(self, collection: str) -> list[QREntry]:
        path = self._path(collection)
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        return [QREntry(**e) for e in data]

    def _save(self, collection: str, entries: list[QREntry]):
        path = self._path(collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([e.to_dict() for e in entries], indent=2, ensure_ascii=False))

    def add(self, collection: str, question: str, answer: str,
            tags: list[str] | None = None, source: str = "manual") -> QREntry:
        entries = self._load(collection)
        entry = QREntry(
            id=str(uuid.uuid4())[:8],
            question=question,
            answer=answer,
            tags=tags or [],
            source=source,
        )
        entries.append(entry)
        self._save(collection, entries)
        return entry

    def list(self, collection: str) -> list[QREntry]:
        return self._load(collection)

    def delete(self, collection: str, entry_id: str):
        entries = self._load(collection)
        entries = [e for e in entries if e.id != entry_id]
        self._save(collection, entries)

    def update(self, collection: str, entry_id: str,
               question: str | None = None, answer: str | None = None,
               tags: list[str] | None = None):
        entries = self._load(collection)
        for e in entries:
            if e.id == entry_id:
                if question is not None:
                    e.question = question
                if answer is not None:
                    e.answer = answer
                if tags is not None:
                    e.tags = tags
                break
        self._save(collection, entries)

    def search(self, collection: str, query: str, threshold: float = 0.7) -> QREntry | None:
        """Search for a matching Q&R entry using text similarity.

        Returns the best match above the threshold, or None.
        Uses SequenceMatcher for simple fuzzy matching (no embeddings needed).
        For production, replace with semantic search via embeddings.
        """
        entries = self._load(collection)
        if not entries:
            return None

        query_lower = query.lower().strip()
        best_match = None
        best_score = 0.0

        for entry in entries:
            # Exact match
            if entry.question.lower().strip() == query_lower:
                self.record_hit(collection)
                return entry

            # Fuzzy match
            score = SequenceMatcher(None, query_lower, entry.question.lower().strip()).ratio()
            if score > best_score:
                best_score = score
                best_match = entry

        if best_match and best_score >= threshold:
            self.record_hit(collection)
            return best_match

        self.record_miss(collection)
        return None

    def import_json(self, collection: str, data: list[dict]):
        """Import Q&R entries from a JSON list."""
        entries = self._load(collection)
        for item in data:
            entries.append(QREntry(
                id=str(uuid.uuid4())[:8],
                question=item["question"],
                answer=item["answer"],
                tags=item.get("tags", []),
                source="import",
            ))
        self._save(collection, entries)

    def export_json(self, collection: str) -> list[dict]:
        """Export Q&R entries as JSON."""
        return [{"question": e.question, "answer": e.answer, "tags": e.tags}
                for e in self._load(collection)]

    def record_hit(self, collection: str):
        stats = self._stats.setdefault(collection, {"hits": 0, "misses": 0})
        stats["hits"] += 1

    def record_miss(self, collection: str):
        stats = self._stats.setdefault(collection, {"hits": 0, "misses": 0})
        stats["misses"] += 1

    def stats(self, collection: str) -> dict:
        entries = self._load(collection)
        s = self._stats.get(collection, {"hits": 0, "misses": 0})
        return {
            "total_entries": len(entries),
            "hits": s["hits"],
            "misses": s["misses"],
            "hit_rate": s["hits"] / (s["hits"] + s["misses"]) if (s["hits"] + s["misses"]) > 0 else 0,
        }
