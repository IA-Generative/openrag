"""Admin router for OpenRAG.

Provides endpoints for:
- Indexing profiles (CRUD + partition assignment)
- Q&A entries (CRUD, import/export, evaluation)
- User feedback (ingestion, review, promotion)
- Drive sources (CRUD + sync triggers)
- Notification channels (CRUD + test)
- Announcements & polls (CRUD + send + vote)
"""

import os
from datetime import datetime

import consts
from components.indexer.vectordb.utils import (
    Announcement,
    DriveFileMapping,
    DriveSource,
    IndexingProfile,
    NotificationChannel,
    Partition,
    PartitionIndexingConfig,
    PollOption,
    PollResponse,
    QAEntry,
    QAEvalRun,
    UserFeedback,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from routers.utils import require_admin
from utils.dependencies import get_vectordb
from utils.logger import get_logger

logger = get_logger()
router = APIRouter()

FEEDBACK_SERVICE_KEY = os.getenv("FEEDBACK_SERVICE_KEY", "")


# --- Pydantic models ---


class IndexingProfileCreate(BaseModel):
    name: str
    description: str | None = None
    chunker_name: str = "recursive_splitter"
    chunk_size: int = 512
    chunk_overlap_rate: float = 0.2
    contextual_retrieval: bool = True
    contextualization_timeout: int = 120
    max_concurrent_contextualization: int = 10
    retriever_type: str = "single"
    retriever_top_k: int = 50
    similarity_threshold: float = 0.6
    extra_params: dict = Field(default_factory=dict)


class PartitionIndexingAssign(BaseModel):
    indexing_profile_id: int
    overrides: dict = Field(default_factory=dict)


class QAEntryCreate(BaseModel):
    partition_name: str | None = None
    question: str
    expected_answer: str | None = None
    override_answer: str | None = None
    override_active: bool = False
    tags: list[str] = Field(default_factory=list)


class QAEvalRequest(BaseModel):
    partition_name: str
    tags: list[str] = Field(default_factory=lambda: ["eval"])
    config: dict = Field(default_factory=dict)


class FeedbackIngestItem(BaseModel):
    external_user_id: str | None = None
    question: str
    response: str
    model: str | None = None
    rating: int = Field(ge=-1, le=1)
    reason: str | None = None
    owui_chat_id: str | None = None
    owui_message_id: str | None = None


class FeedbackIngestRequest(BaseModel):
    feedbacks: list[FeedbackIngestItem]


class FeedbackPromoteRequest(BaseModel):
    type: str = Field(pattern="^(override|eval)$")
    override_answer: str | None = None
    expected_answer: str | None = None
    tags: list[str] = Field(default_factory=list)
    activate_override: bool = False


class DriveSourceCreate(BaseModel):
    partition_name: str
    drive_base_url: str
    drive_folder_id: str
    sync_frequency_minutes: int = 60
    auth_mode: str = "service_account"
    service_account_client_id: str | None = None
    service_account_client_secret: str | None = None


class ChannelCreate(BaseModel):
    name: str
    type: str = Field(pattern="^(webhook|email_smtp|tchap_bot)$")
    config: dict
    active: bool = True


class AnnouncementCreate(BaseModel):
    type: str = Field(pattern="^(announcement|poll)$")
    title: str
    body: str
    target_type: str = Field(pattern="^(all|partition|group|user)$")
    target_value: str | None = None
    scheduled_at: datetime | None = None
    channels: list[int] = Field(default_factory=list)
    poll_options: list[str] = Field(default_factory=list)


class PollVoteRequest(BaseModel):
    poll_option_id: int


# --- Helper to get a DB session from the vectordb actor ---


async def get_session():
    """Get a SQLAlchemy session from the vectordb actor's partition file manager."""
    vectordb = get_vectordb()
    pfm = await vectordb.get_partition_file_manager.remote()
    return pfm.Session


# ============================================================
# INDEXING PROFILES
# ============================================================


@router.get("/indexing-profiles")
async def list_indexing_profiles(user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        profiles = s.query(IndexingProfile).all()
        return [p.to_dict() for p in profiles]


@router.post("/indexing-profiles", status_code=201)
async def create_indexing_profile(body: IndexingProfileCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        existing = s.query(IndexingProfile).filter_by(name=body.name).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Profile '{body.name}' already exists")
        profile = IndexingProfile(
            name=body.name,
            description=body.description,
            chunker_name=body.chunker_name,
            chunk_size=body.chunk_size,
            chunk_overlap_rate=str(body.chunk_overlap_rate),
            contextual_retrieval=body.contextual_retrieval,
            contextualization_timeout=body.contextualization_timeout,
            max_concurrent_contextualization=body.max_concurrent_contextualization,
            retriever_type=body.retriever_type,
            retriever_top_k=body.retriever_top_k,
            similarity_threshold=str(body.similarity_threshold),
            extra_params=body.extra_params,
        )
        s.add(profile)
        s.commit()
        s.refresh(profile)
        return profile.to_dict()


@router.get("/indexing-profiles/{profile_id}")
async def get_indexing_profile(profile_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        profile = s.query(IndexingProfile).filter_by(id=profile_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile.to_dict()


@router.put("/indexing-profiles/{profile_id}")
async def update_indexing_profile(profile_id: int, body: IndexingProfileCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        profile = s.query(IndexingProfile).filter_by(id=profile_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        for field_name in body.model_fields:
            value = getattr(body, field_name)
            if field_name in ("chunk_overlap_rate", "similarity_threshold"):
                value = str(value)
            setattr(profile, field_name, value)
        profile.updated_at = datetime.now()
        s.commit()
        s.refresh(profile)
        return profile.to_dict()


@router.delete("/indexing-profiles/{profile_id}")
async def delete_indexing_profile(profile_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        # Check if in use
        in_use = s.query(PartitionIndexingConfig).filter_by(indexing_profile_id=profile_id).first()
        if in_use:
            raise HTTPException(status_code=409, detail="Profile is in use by a partition and cannot be deleted")
        profile = s.query(IndexingProfile).filter_by(id=profile_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        s.delete(profile)
        s.commit()
        return {"detail": "Profile deleted"}


@router.get("/partitions/{partition_name}/indexing")
async def get_partition_indexing(partition_name: str, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        config = s.query(PartitionIndexingConfig).filter_by(partition_name=partition_name).first()
        if not config:
            return {"partition_name": partition_name, "indexing_profile_id": None, "overrides": {}}
        return {
            "partition_name": config.partition_name,
            "indexing_profile_id": config.indexing_profile_id,
            "overrides": config.overrides,
            "profile": config.profile.to_dict() if config.profile else None,
        }


@router.put("/partitions/{partition_name}/indexing")
async def set_partition_indexing(partition_name: str, body: PartitionIndexingAssign, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        # Verify profile exists
        profile = s.query(IndexingProfile).filter_by(id=body.indexing_profile_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Indexing profile not found")

        config = s.query(PartitionIndexingConfig).filter_by(partition_name=partition_name).first()
        if config:
            config.indexing_profile_id = body.indexing_profile_id
            config.overrides = body.overrides
        else:
            config = PartitionIndexingConfig(
                partition_name=partition_name,
                indexing_profile_id=body.indexing_profile_id,
                overrides=body.overrides,
            )
            s.add(config)
        s.commit()
        return {"detail": "Partition indexing config updated"}


# ============================================================
# Q&A ENTRIES
# ============================================================


@router.get("/qa")
async def list_qa_entries(
    partition: str | None = None,
    tags: str | None = None,
    override_active: bool | None = None,
    page: int = 1,
    per_page: int = 50,
    user=Depends(require_admin),
):
    Session = await get_session()
    with Session() as s:
        query = s.query(QAEntry)
        if partition:
            query = query.filter(QAEntry.partition_name == partition)
        if override_active is not None:
            query = query.filter(QAEntry.override_active == override_active)
        # tags filter: match entries that contain any of the requested tags
        if tags:
            tag_list = [t.strip() for t in tags.split(",")]
            for tag in tag_list:
                query = query.filter(QAEntry.tags.contains([tag]))

        total = query.count()
        entries = query.offset((page - 1) * per_page).limit(per_page).all()
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "entries": [e.to_dict() for e in entries],
        }


@router.post("/qa", status_code=201)
async def create_qa_entry(body: QAEntryCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        entry = QAEntry(
            partition_name=body.partition_name,
            question=body.question,
            expected_answer=body.expected_answer,
            override_answer=body.override_answer,
            override_active=body.override_active,
            tags=body.tags,
            created_by=user.get("id"),
        )
        s.add(entry)
        s.commit()
        s.refresh(entry)
        return entry.to_dict()


@router.get("/qa/{qa_id}")
async def get_qa_entry(qa_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        entry = s.query(QAEntry).filter_by(id=qa_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Q&A entry not found")
        return entry.to_dict()


@router.put("/qa/{qa_id}")
async def update_qa_entry(qa_id: int, body: QAEntryCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        entry = s.query(QAEntry).filter_by(id=qa_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Q&A entry not found")
        entry.partition_name = body.partition_name
        entry.question = body.question
        entry.expected_answer = body.expected_answer
        entry.override_answer = body.override_answer
        entry.override_active = body.override_active
        entry.tags = body.tags
        entry.updated_at = datetime.now()
        s.commit()
        s.refresh(entry)
        return entry.to_dict()


@router.delete("/qa/{qa_id}")
async def delete_qa_entry(qa_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        entry = s.query(QAEntry).filter_by(id=qa_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Q&A entry not found")
        s.delete(entry)
        s.commit()
        return {"detail": "Q&A entry deleted"}


@router.post("/qa/import", status_code=201)
async def import_qa_entries(entries: list[QAEntryCreate], user=Depends(require_admin)):
    Session = await get_session()
    created = 0
    with Session() as s:
        for body in entries:
            entry = QAEntry(
                partition_name=body.partition_name,
                question=body.question,
                expected_answer=body.expected_answer,
                override_answer=body.override_answer,
                override_active=body.override_active,
                tags=body.tags,
                created_by=user.get("id"),
            )
            s.add(entry)
            created += 1
        s.commit()
    return {"detail": f"Imported {created} Q&A entries"}


@router.get("/qa/export")
async def export_qa_entries(partition: str | None = None, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        query = s.query(QAEntry)
        if partition:
            query = query.filter(QAEntry.partition_name == partition)
        entries = query.all()
        return [e.to_dict() for e in entries]


# --- Evaluation ---


@router.post("/qa/eval", status_code=201)
async def start_eval_run(body: QAEvalRequest, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        # Count matching questions
        query = s.query(QAEntry).filter(QAEntry.partition_name == body.partition_name)
        for tag in body.tags:
            query = query.filter(QAEntry.tags.contains([tag]))
        total = query.count()

        if total == 0:
            raise HTTPException(status_code=404, detail="No Q&A entries match the filters")

        run = QAEvalRun(
            partition_name=body.partition_name,
            status="pending",
            total_questions=total,
            config_json=body.config,
            created_by=user.get("id"),
        )
        s.add(run)
        s.commit()
        s.refresh(run)

        # TODO: Launch async evaluation task via Ray
        # For now, return the run ID for polling
        return run.to_dict()


@router.get("/qa/eval/runs")
async def list_eval_runs(user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        runs = s.query(QAEvalRun).order_by(QAEvalRun.started_at.desc()).all()
        return [r.to_dict() for r in runs]


@router.get("/qa/eval/runs/{run_id}")
async def get_eval_run(run_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        run = s.query(QAEvalRun).filter_by(id=run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Eval run not found")
        return run.to_dict()


# ============================================================
# USER FEEDBACK
# ============================================================


def _require_service_key(request: Request):
    """Verify the service key for feedback ingestion."""
    if not FEEDBACK_SERVICE_KEY:
        return  # No key configured = open
    key = request.headers.get("x-service-key", "")
    if key != FEEDBACK_SERVICE_KEY:
        raise HTTPException(status_code=403, detail="Invalid service key")


def _partition_from_model(model: str | None) -> str | None:
    """Extract partition name from model string like 'openrag-finance'."""
    if not model:
        return None
    prefix = consts.PARTITION_PREFIX
    if model.startswith(prefix):
        partition = model[len(prefix):]
        return None if partition == "all" else partition
    legacy = consts.LEGACY_PARTITION_PREFIX
    if model.startswith(legacy):
        partition = model[len(legacy):]
        return None if partition == "all" else partition
    return None


@router.post("/feedback/ingest")
async def ingest_feedback(body: FeedbackIngestRequest, request: Request):
    _require_service_key(request)
    Session = await get_session()
    ingested = 0
    skipped = 0
    with Session() as s:
        for fb in body.feedbacks:
            # Deduplicate
            if fb.owui_chat_id and fb.owui_message_id:
                existing = s.query(UserFeedback).filter_by(
                    owui_chat_id=fb.owui_chat_id,
                    owui_message_id=fb.owui_message_id,
                ).first()
                if existing:
                    skipped += 1
                    continue

            partition = _partition_from_model(fb.model)
            entry = UserFeedback(
                external_user_id=fb.external_user_id,
                partition_name=partition,
                question=fb.question,
                response=fb.response,
                model=fb.model,
                rating=fb.rating,
                reason=fb.reason,
                owui_chat_id=fb.owui_chat_id,
                owui_message_id=fb.owui_message_id,
            )
            s.add(entry)
            ingested += 1
        s.commit()
    return {"ingested": ingested, "skipped": skipped}


@router.get("/feedback")
async def list_feedback(
    partition: str | None = None,
    rating: int | None = None,
    feedback_status: str | None = None,
    page: int = 1,
    per_page: int = 50,
    user=Depends(require_admin),
):
    Session = await get_session()
    with Session() as s:
        query = s.query(UserFeedback).order_by(UserFeedback.created_at.desc())
        if partition:
            query = query.filter(UserFeedback.partition_name == partition)
        if rating is not None:
            query = query.filter(UserFeedback.rating == rating)
        if feedback_status:
            query = query.filter(UserFeedback.status == feedback_status)
        total = query.count()
        entries = query.offset((page - 1) * per_page).limit(per_page).all()
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "entries": [e.to_dict() for e in entries],
        }


@router.get("/feedback/stats")
async def feedback_stats(user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        from sqlalchemy import case, func

        total = s.query(func.count(UserFeedback.id)).scalar()
        positive = s.query(func.count(UserFeedback.id)).filter(UserFeedback.rating == 1).scalar()
        negative = s.query(func.count(UserFeedback.id)).filter(UserFeedback.rating == -1).scalar()
        pending = s.query(func.count(UserFeedback.id)).filter(UserFeedback.status == "pending").scalar()

        # Per partition
        by_partition = (
            s.query(
                UserFeedback.partition_name,
                func.count(UserFeedback.id).label("total"),
                func.count(case((UserFeedback.rating == 1, 1))).label("positive"),
                func.count(case((UserFeedback.rating == -1, 1))).label("negative"),
            )
            .group_by(UserFeedback.partition_name)
            .all()
        )

        return {
            "global": {
                "total": total,
                "positive": positive,
                "negative": negative,
                "satisfaction_rate": round(positive / total, 2) if total else 0,
            },
            "by_partition": [
                {
                    "partition": row.partition_name,
                    "total": row.total,
                    "positive": row.positive,
                    "negative": row.negative,
                    "rate": round(row.positive / row.total, 2) if row.total else 0,
                }
                for row in by_partition
            ],
            "pending_review": pending,
        }


@router.patch("/feedback/{feedback_id}")
async def review_feedback(feedback_id: int, feedback_status: str, user=Depends(require_admin)):
    if feedback_status not in ("reviewed", "dismissed"):
        raise HTTPException(status_code=400, detail="Status must be 'reviewed' or 'dismissed'")
    Session = await get_session()
    with Session() as s:
        fb = s.query(UserFeedback).filter_by(id=feedback_id).first()
        if not fb:
            raise HTTPException(status_code=404, detail="Feedback not found")
        fb.status = feedback_status
        fb.reviewed_by = user.get("id")
        fb.reviewed_at = datetime.now()
        s.commit()
        return {"detail": "Feedback updated"}


@router.post("/feedback/{feedback_id}/promote")
async def promote_feedback(feedback_id: int, body: FeedbackPromoteRequest, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        fb = s.query(UserFeedback).filter_by(id=feedback_id).first()
        if not fb:
            raise HTTPException(status_code=404, detail="Feedback not found")

        qa = QAEntry(
            partition_name=fb.partition_name,
            question=fb.question,
            tags=body.tags,
            source_feedback_id=fb.id,
            created_by=user.get("id"),
        )

        if body.type == "override":
            qa.override_answer = body.override_answer or fb.response
            qa.override_active = body.activate_override
        else:  # eval
            qa.expected_answer = body.expected_answer or fb.response

        s.add(qa)
        s.flush()

        fb.status = "promoted"
        fb.promoted_to_qa_id = qa.id
        fb.reviewed_by = user.get("id")
        fb.reviewed_at = datetime.now()
        s.commit()
        s.refresh(qa)
        return qa.to_dict()


# ============================================================
# DRIVE SOURCES
# ============================================================


@router.get("/drive-sources")
async def list_drive_sources(user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        sources = s.query(DriveSource).all()
        return [src.to_dict() for src in sources]


@router.post("/drive-sources", status_code=201)
async def create_drive_source(body: DriveSourceCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        source = DriveSource(
            partition_name=body.partition_name,
            drive_base_url=body.drive_base_url,
            drive_folder_id=body.drive_folder_id,
            sync_frequency_minutes=body.sync_frequency_minutes,
            auth_mode=body.auth_mode,
            service_account_client_id=body.service_account_client_id,
            service_account_client_secret=body.service_account_client_secret,
            created_by=user.get("id"),
        )
        s.add(source)
        s.commit()
        s.refresh(source)
        return source.to_dict()


@router.get("/drive-sources/{source_id}")
async def get_drive_source(source_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        source = s.query(DriveSource).filter_by(id=source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Drive source not found")
        result = source.to_dict()
        result["file_mappings"] = [m.to_dict() for m in source.file_mappings]
        return result


@router.put("/drive-sources/{source_id}")
async def update_drive_source(source_id: int, body: DriveSourceCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        source = s.query(DriveSource).filter_by(id=source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Drive source not found")
        source.partition_name = body.partition_name
        source.drive_base_url = body.drive_base_url
        source.drive_folder_id = body.drive_folder_id
        source.sync_frequency_minutes = body.sync_frequency_minutes
        source.auth_mode = body.auth_mode
        source.service_account_client_id = body.service_account_client_id
        source.service_account_client_secret = body.service_account_client_secret
        s.commit()
        s.refresh(source)
        return source.to_dict()


@router.delete("/drive-sources/{source_id}")
async def delete_drive_source(source_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        source = s.query(DriveSource).filter_by(id=source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Drive source not found")
        # TODO: Also delete indexed files from partition via Indexer
        s.delete(source)
        s.commit()
        return {"detail": "Drive source deleted"}


@router.post("/drive-sources/{source_id}/sync")
async def trigger_drive_sync(source_id: int, user=Depends(require_admin)):
    """Trigger a manual sync for a drive source."""
    Session = await get_session()
    with Session() as s:
        source = s.query(DriveSource).filter_by(id=source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Drive source not found")

    # TODO: Trigger via DriveSyncScheduler Ray actor
    # scheduler = ray.get_actor("DriveSyncScheduler", namespace="openrag")
    # await scheduler.trigger_sync.remote(source_id)

    return {"detail": f"Sync triggered for source {source_id}"}


# ============================================================
# NOTIFICATION CHANNELS
# ============================================================


@router.get("/channels")
async def list_channels(user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        channels = s.query(NotificationChannel).all()
        return [c.to_dict() for c in channels]


@router.post("/channels", status_code=201)
async def create_channel(body: ChannelCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        channel = NotificationChannel(
            name=body.name,
            type=body.type,
            config_json=body.config,
            active=body.active,
        )
        s.add(channel)
        s.commit()
        s.refresh(channel)
        return channel.to_dict()


@router.put("/channels/{channel_id}")
async def update_channel(channel_id: int, body: ChannelCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        channel = s.query(NotificationChannel).filter_by(id=channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        channel.name = body.name
        channel.type = body.type
        channel.config_json = body.config
        channel.active = body.active
        s.commit()
        s.refresh(channel)
        return channel.to_dict()


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        channel = s.query(NotificationChannel).filter_by(id=channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
        s.delete(channel)
        s.commit()
        return {"detail": "Channel deleted"}


@router.post("/channels/{channel_id}/test")
async def test_channel(channel_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        channel = s.query(NotificationChannel).filter_by(id=channel_id).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

    # TODO: Use dispatcher to send test message
    # from components.notifications import get_dispatcher
    # dispatcher = get_dispatcher(channel)
    # await dispatcher.send_test()

    return {"detail": f"Test message sent via {channel.type} channel '{channel.name}'"}


# ============================================================
# ANNOUNCEMENTS & POLLS
# ============================================================


@router.get("/announcements")
async def list_announcements(
    announcement_type: str | None = None,
    announcement_status: str | None = None,
    user=Depends(require_admin),
):
    Session = await get_session()
    with Session() as s:
        query = s.query(Announcement).order_by(Announcement.created_at.desc())
        if announcement_type:
            query = query.filter(Announcement.type == announcement_type)
        if announcement_status:
            query = query.filter(Announcement.status == announcement_status)
        items = query.all()
        return [a.to_dict() for a in items]


@router.post("/announcements", status_code=201)
async def create_announcement(body: AnnouncementCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        ann = Announcement(
            type=body.type,
            title=body.title,
            body=body.body,
            target_type=body.target_type,
            target_value=body.target_value,
            scheduled_at=body.scheduled_at,
            channels=body.channels,
            created_by=user.get("id"),
            status="scheduled" if body.scheduled_at else "draft",
        )
        s.add(ann)
        s.flush()

        # Add poll options if it's a poll
        if body.type == "poll":
            for i, label in enumerate(body.poll_options):
                s.add(PollOption(announcement_id=ann.id, label=label, sort_order=i))

        s.commit()
        s.refresh(ann)
        return ann.to_dict()


@router.get("/announcements/{ann_id}")
async def get_announcement(ann_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        ann = s.query(Announcement).filter_by(id=ann_id).first()
        if not ann:
            raise HTTPException(status_code=404, detail="Announcement not found")
        return ann.to_dict()


@router.put("/announcements/{ann_id}")
async def update_announcement(ann_id: int, body: AnnouncementCreate, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        ann = s.query(Announcement).filter_by(id=ann_id).first()
        if not ann:
            raise HTTPException(status_code=404, detail="Announcement not found")
        if ann.status != "draft":
            raise HTTPException(status_code=400, detail="Only draft announcements can be edited")
        ann.title = body.title
        ann.body = body.body
        ann.target_type = body.target_type
        ann.target_value = body.target_value
        ann.scheduled_at = body.scheduled_at
        ann.channels = body.channels
        ann.updated_at = datetime.now()
        s.commit()
        s.refresh(ann)
        return ann.to_dict()


@router.delete("/announcements/{ann_id}")
async def delete_announcement(ann_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        ann = s.query(Announcement).filter_by(id=ann_id).first()
        if not ann:
            raise HTTPException(status_code=404, detail="Announcement not found")
        s.delete(ann)
        s.commit()
        return {"detail": "Announcement deleted"}


@router.post("/announcements/{ann_id}/send")
async def send_announcement(ann_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        ann = s.query(Announcement).filter_by(id=ann_id).first()
        if not ann:
            raise HTTPException(status_code=404, detail="Announcement not found")
        if ann.status == "sent":
            raise HTTPException(status_code=400, detail="Already sent")

        # TODO: Dispatch via configured channels
        ann.status = "sent"
        ann.sent_at = datetime.now()
        s.commit()
        return {"detail": "Announcement sent"}


@router.post("/announcements/{ann_id}/close")
async def close_announcement(ann_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        ann = s.query(Announcement).filter_by(id=ann_id).first()
        if not ann:
            raise HTTPException(status_code=404, detail="Announcement not found")
        ann.status = "closed"
        ann.closed_at = datetime.now()
        s.commit()
        return {"detail": "Announcement closed"}


@router.get("/announcements/{ann_id}/results")
async def get_poll_results(ann_id: int, user=Depends(require_admin)):
    Session = await get_session()
    with Session() as s:
        ann = s.query(Announcement).filter_by(id=ann_id).first()
        if not ann or ann.type != "poll":
            raise HTTPException(status_code=404, detail="Poll not found")

        from sqlalchemy import func

        results = (
            s.query(PollOption.id, PollOption.label, func.count(PollResponse.id).label("votes"))
            .outerjoin(PollResponse, PollOption.id == PollResponse.poll_option_id)
            .filter(PollOption.announcement_id == ann_id)
            .group_by(PollOption.id, PollOption.label)
            .order_by(PollOption.sort_order)
            .all()
        )

        total_votes = sum(r.votes for r in results)
        return {
            "announcement_id": ann_id,
            "total_votes": total_votes,
            "options": [
                {"id": r.id, "label": r.label, "votes": r.votes}
                for r in results
            ],
        }


# --- Public endpoints (user-facing) ---


@router.post("/announcements/{ann_id}/respond")
async def vote_on_poll(ann_id: int, body: PollVoteRequest, request: Request):
    """Vote on a poll. Requires authentication but not admin."""
    user = request.state.user
    external_id = user.get("external_user_id") or str(user.get("id"))

    Session = await get_session()
    with Session() as s:
        ann = s.query(Announcement).filter_by(id=ann_id).first()
        if not ann or ann.type != "poll":
            raise HTTPException(status_code=404, detail="Poll not found")
        if ann.status == "closed":
            raise HTTPException(status_code=400, detail="Poll is closed")

        # Verify option belongs to this poll
        option = s.query(PollOption).filter_by(id=body.poll_option_id, announcement_id=ann_id).first()
        if not option:
            raise HTTPException(status_code=404, detail="Poll option not found")

        # Check for existing vote
        existing = s.query(PollResponse).filter_by(
            announcement_id=ann_id, external_user_id=external_id
        ).first()
        if existing:
            # Update vote
            existing.poll_option_id = body.poll_option_id
            existing.responded_at = datetime.now()
        else:
            s.add(PollResponse(
                announcement_id=ann_id,
                poll_option_id=body.poll_option_id,
                external_user_id=external_id,
            ))
        s.commit()
        return {"detail": "Vote recorded"}
