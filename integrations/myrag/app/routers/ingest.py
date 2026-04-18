"""Ingest router — async upload + intelligent chunking + OpenRAG indexing."""

import asyncio

from fastapi import APIRouter, File, Form, Query, UploadFile, HTTPException

from app.services.chunker import chunk_document, Strategy, Sensitivity
from app.services.job_tracker import create_job, get_job, list_jobs
from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])


async def _upload_chunks_background(job_id: str, collection: str, chunks: list[dict]):
    """Background task: upload chunks to OpenRAG one by one, updating job progress."""
    from app.services.job_tracker import get_job

    job = get_job(job_id)
    if not job:
        return

    job.status = "uploading"
    client = OpenRAGClient()

    for i, chunk in enumerate(chunks):
        try:
            await client.upload_chunk(collection, chunk)
            job.uploaded_chunks = i + 1
        except Exception as e:
            job.failed_chunks += 1
            job.uploaded_chunks = i + 1

    job.status = "done" if job.failed_chunks == 0 else "done_with_errors"


@router.post("/{collection}")
async def ingest_file(
    collection: str,
    file: UploadFile = File(...),
    strategy: Strategy = Form("auto"),
    sensitivity: Sensitivity = Form("public"),
    max_chars: int = Form(512),
    overlap: int = Form(50),
):
    """Upload a file, chunk it intelligently, and index in OpenRAG.

    Returns immediately with a job_id. Track progress via GET /api/ingest/jobs/{job_id}.

    Sensitivity levels: public, internal, restricted, confidential, secret.
    Each chunk carries the sensitivity in its metadata for access control filtering.
    """
    content = await file.read()
    text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty file")

    # Chunk the document (synchronous, fast)
    chunks = chunk_document(
        text,
        strategy=strategy,
        max_chars=max_chars,
        overlap=overlap,
        sensitivity=sensitivity,
    )
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks produced")

    # Create partition in OpenRAG (idempotent)
    client = OpenRAGClient()
    await client.create_partition(collection)

    # Create job and start background upload
    job = create_job(
        collection=collection,
        filename=file.filename or "unknown",
        strategy=strategy,
        sensitivity=sensitivity,
    )
    job.total_chunks = len(chunks)

    # Fire and forget — upload in background
    asyncio.create_task(_upload_chunks_background(job.job_id, collection, chunks))

    return {
        "job_id": job.job_id,
        "collection": collection,
        "strategy": strategy,
        "sensitivity": sensitivity,
        "total_chunks": len(chunks),
        "status": "chunking_done",
        "track_url": f"/api/ingest/jobs/{job.job_id}",
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Track ingestion progress for a job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.get("/jobs")
async def list_all_jobs(collection: str | None = Query(None)):
    """List all ingestion jobs, optionally filtered by collection."""
    return {"jobs": list_jobs(collection=collection)}
