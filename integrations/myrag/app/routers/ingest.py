"""Ingest router — async upload + intelligent chunking + OpenRAG indexing."""

import asyncio
import hashlib
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, File, Form, Query, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.services.chunker import chunk_document, Strategy, Sensitivity
from app.services.job_store import create_job, get_job, update_job, increment_job_progress, complete_job, list_jobs
from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])
logger = logging.getLogger("myrag.ingest")

# R7 — Source file storage directory
SOURCES_DIR = Path(settings.data_dir) / "_sources"


def _save_source_file(collection: str, filename: str, content: bytes) -> str:
    """Save source file to disk for re-indexation (R7). Returns the storage path."""
    col_dir = SOURCES_DIR / collection
    col_dir.mkdir(parents=True, exist_ok=True)
    path = col_dir / filename
    path.write_bytes(content)
    return str(path)


async def _upload_chunks_background(job_id: str, collection: str, chunks: list[dict]):
    """Background task: upload chunks to OpenRAG, updating job progress in DB."""
    client = OpenRAGClient(timeout=120.0)

    await update_job(job_id, status="uploading")

    for i, chunk in enumerate(chunks):
        success = True
        try:
            await client.upload_chunk(collection, chunk)
        except Exception as e:
            success = False
            logger.warning(f"Job {job_id} chunk {i+1}/{len(chunks)} failed: {e}")

        await increment_job_progress(job_id, success=success)

        if (i + 1) % 100 == 0:
            logger.info(f"Job {job_id}: {i+1}/{len(chunks)} uploaded")

    await complete_job(job_id)
    job = await get_job(job_id)
    logger.info(f"Job {job_id} finished: {job}")


async def _ingest_content(
    collection: str, filename: str, content: bytes,
    strategy: str, sensitivity: str, source_path: str = "",
) -> dict:
    """Common ingest logic for file upload and URL fetch."""
    text = content.decode("utf-8", errors="replace")
    if not text.strip():
        raise HTTPException(status_code=400, detail="Fichier vide")

    chunks = chunk_document(text, strategy=strategy, max_chars=512, overlap=50, sensitivity=sensitivity)
    if not chunks:
        raise HTTPException(status_code=400, detail="Aucun chunk produit")

    # Create partition in OpenRAG (best-effort)
    client = OpenRAGClient()
    try:
        await client.create_partition(collection)
    except Exception:
        pass

    # R7 — Save source file
    saved_path = _save_source_file(collection, filename, content)

    # Record source file in DB
    from app.database import async_session
    from app.models.db import SourceFile
    checksum = hashlib.sha256(content).hexdigest()
    async with async_session() as session:
        sf = SourceFile(
            collection_name=collection,
            filename=filename,
            original_url=source_path if source_path.startswith("http") else "",
            storage_path=saved_path,
            file_size=len(content),
            checksum=checksum,
            strategy_used=strategy,
            chunks_produced=len(chunks),
        )
        session.add(sf)
        await session.commit()

    # Create job in DB and start background upload
    job = await create_job(
        collection=collection,
        filename=filename,
        strategy=strategy,
        sensitivity=sensitivity,
        source_path=saved_path,
    )
    await update_job(job["job_id"], total_chunks=len(chunks))

    asyncio.create_task(_upload_chunks_background(job["job_id"], collection, chunks))

    return {
        "job_id": job["job_id"],
        "collection": collection,
        "filename": filename,
        "strategy": strategy,
        "sensitivity": sensitivity,
        "total_chunks": len(chunks),
        "status": "chunking_done",
        "track_url": f"/api/ingest/jobs/{job['job_id']}",
    }


@router.post("/{collection}")
async def ingest_file(
    collection: str,
    file: UploadFile = File(...),
    strategy: Strategy = Form("auto"),
    sensitivity: Sensitivity = Form("public"),
    max_chars: int = Form(512),
    overlap: int = Form(50),
):
    """Upload a file, chunk it intelligently, and index in OpenRAG."""
    content = await file.read()
    return await _ingest_content(
        collection=collection,
        filename=file.filename or "unknown",
        content=content,
        strategy=strategy,
        sensitivity=sensitivity,
    )


class IngestFromUrlRequest(BaseModel):
    url: str
    strategy: Strategy = "auto"
    sensitivity: Sensitivity = "public"


@router.post("/{collection}/from-url")
async def ingest_from_url(collection: str, req: IngestFromUrlRequest):
    """Download a remote file by URL, chunk it, and index in OpenRAG."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            resp = await client.get(req.url)
            if resp.status_code >= 400:
                raise HTTPException(status_code=400, detail=f"HTTP {resp.status_code}")
            content = resp.content
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Timeout")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filename = req.url.rstrip("/").split("/")[-1] or "remote-file"

    return await _ingest_content(
        collection=collection,
        filename=filename,
        content=content,
        strategy=req.strategy,
        sensitivity=req.sensitivity,
        source_path=req.url,
    )


@router.post("/{collection}/reindex")
async def reindex_collection(collection: str, strategy: Strategy = "auto", sensitivity: Sensitivity = "public"):
    """Re-index all source files of a collection with a new strategy.

    Uses source files saved by R7 to re-chunk and re-index without re-upload.
    """
    from app.models.db import SourceFile
    from app.database import async_session as db_session

    # Get all source files for this collection
    async with db_session() as session:
        result = await session.execute(
            select(SourceFile).where(SourceFile.collection_name == collection)
        )
        source_files = result.scalars().all()

    if not source_files:
        raise HTTPException(status_code=400, detail="Aucun fichier source enregistre pour cette collection. Re-uploadez vos documents.")

    # Delete existing partition and recreate
    client = OpenRAGClient()
    try:
        await client._post(f"/partition/{collection}", json=None)  # create if not exists
    except Exception:
        pass

    # Re-ingest each source file
    total_jobs = []
    for sf in source_files:
        path = Path(sf.storage_path)
        if not path.exists():
            logger.warning(f"Source file missing: {sf.storage_path}")
            continue

        content = path.read_bytes()
        result = await _ingest_content(
            collection=collection,
            filename=sf.filename,
            content=content,
            strategy=strategy,
            sensitivity=sensitivity,
            source_path=sf.storage_path,
        )
        total_jobs.append(result)

    return {
        "status": "reindexing",
        "collection": collection,
        "strategy": strategy,
        "files_reindexed": len(total_jobs),
        "jobs": [j["job_id"] for j in total_jobs],
    }


@router.get("/{collection}/sources")
async def list_source_files(collection: str):
    """List all stored source files for a collection."""
    from app.models.db import SourceFile
    from app.database import async_session as db_session

    async with db_session() as session:
        result = await session.execute(
            select(SourceFile).where(SourceFile.collection_name == collection)
            .order_by(SourceFile.created_at.desc())
        )
        files = result.scalars().all()
        return {"sources": [f.to_dict() for f in files]}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs")
async def list_all_jobs(collection: str | None = Query(None)):
    return {"jobs": await list_jobs(collection=collection)}
