"""SQLAlchemy models for MyRAG persistent storage."""

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Collection(Base):
    __tablename__ = "collections"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="")
    strategy: Mapped[str] = mapped_column(String(50), default="auto")
    sensitivity: Mapped[str] = mapped_column(String(50), default="public")
    prompt_template: Mapped[str] = mapped_column(String(100), default="generic")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    graph_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_summary_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_summary_threshold: Mapped[int] = mapped_column(Integer, default=1000)
    scope: Mapped[str] = mapped_column(String(50), default="group")
    contact_name: Mapped[str] = mapped_column(String(255), default="")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(50), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "strategy": self.strategy,
            "sensitivity": self.sensitivity,
            "prompt_template": self.prompt_template,
            "system_prompt": self.system_prompt,
            "graph_enabled": self.graph_enabled,
            "ai_summary_enabled": self.ai_summary_enabled,
            "ai_summary_threshold": self.ai_summary_threshold,
            "scope": self.scope,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
        }


class Publication(Base):
    __tablename__ = "publications"

    collection_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    state: Mapped[str] = mapped_column(String(50), default="draft")
    alias_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    alias_name: Mapped[str] = mapped_column(String(255), default="")
    tool_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    embed_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(50), default="group")
    visibility_groups_json: Mapped[str] = mapped_column(Text, default="[]")
    widget_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    browser_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[str] = mapped_column(String(255), default="")

    def to_dict(self) -> dict:
        return {
            "collection": self.collection_name,
            "state": self.state,
            "alias_enabled": self.alias_enabled,
            "alias_name": self.alias_name,
            "tool_enabled": self.tool_enabled,
            "embed_enabled": self.embed_enabled,
            "visibility": self.visibility,
            "visibility_groups": json.loads(self.visibility_groups_json or "[]"),
            "widget_enabled": self.widget_enabled,
            "browser_enabled": self.browser_enabled,
            "published_at": self.published_at.isoformat() if self.published_at else "",
            "published_by": self.published_by,
        }


class PublicationHistory(Base):
    __tablename__ = "publication_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(50))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    acted_by: Mapped[str] = mapped_column(String(255), default="")
    acted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    job_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    filename: Mapped[str] = mapped_column(String(500), default="")
    source_path: Mapped[str] = mapped_column(Text, default="")
    strategy: Mapped[str] = mapped_column(String(50), default="auto")
    sensitivity: Mapped[str] = mapped_column(String(50), default="public")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_chunks: Mapped[int] = mapped_column(Integer, default=0)
    failed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def progress_pct(self) -> int:
        if self.total_chunks == 0:
            return 0
        return int(self.uploaded_chunks / self.total_chunks * 100)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "collection": self.collection_name,
            "filename": self.filename,
            "source_path": self.source_path,
            "strategy": self.strategy,
            "sensitivity": self.sensitivity,
            "status": self.status,
            "total_chunks": self.total_chunks,
            "uploaded_chunks": self.uploaded_chunks,
            "failed_chunks": self.failed_chunks,
            "progress_pct": self.progress_pct,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "completed_at": self.completed_at.isoformat() if self.completed_at else "",
        }


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    question: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer, default=0)  # -1, 0, 1
    reason: Mapped[str] = mapped_column(Text, default="")
    owui_chat_id: Mapped[str] = mapped_column(String(255), default="")
    owui_message_id: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    promoted_to: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "question": self.question,
            "response": self.response,
            "rating": self.rating,
            "reason": self.reason,
            "status": self.status,
            "promoted_to": self.promoted_to,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class EvalDataset(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    questions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "name": self.name,
            "description": self.description,
            "questions": json.loads(self.questions_json or "[]"),
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    dataset_id: Mapped[int] = mapped_column(Integer)
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "dataset_id": self.dataset_id,
            "results": json.loads(self.results_json or "[]"),
            "score": self.score,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class SourceFile(Base):
    """R7 — Stored source files for re-indexation."""
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_name: Mapped[str] = mapped_column(String(255), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    original_url: Mapped[str] = mapped_column(Text, default="")
    storage_path: Mapped[str] = mapped_column(Text)  # local path or S3 key
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(255), default="")
    checksum: Mapped[str] = mapped_column(String(64), default="")  # SHA-256
    strategy_used: Mapped[str] = mapped_column(String(50), default="auto")
    chunks_produced: Mapped[int] = mapped_column(Integer, default=0)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "collection": self.collection_name,
            "filename": self.filename,
            "original_url": self.original_url,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "strategy_used": self.strategy_used,
            "chunks_produced": self.chunks_produced,
            "last_indexed_at": self.last_indexed_at.isoformat() if self.last_indexed_at else "",
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }
