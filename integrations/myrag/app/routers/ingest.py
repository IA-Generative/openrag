"""Ingest router — upload + intelligent chunking + OpenRAG indexing."""

from fastapi import APIRouter, File, Form, UploadFile, HTTPException

from app.services.chunker import chunk_document, Strategy
from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])


@router.post("/{collection}")
async def ingest_file(
    collection: str,
    file: UploadFile = File(...),
    strategy: Strategy = Form("auto"),
    max_chars: int = Form(512),
    overlap: int = Form(50),
):
    """Upload a file, chunk it intelligently, and index in OpenRAG."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty file")

    # Chunk the document
    chunks = chunk_document(text, strategy=strategy, max_chars=max_chars, overlap=overlap)
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks produced")

    # Create partition in OpenRAG (idempotent)
    client = OpenRAGClient()
    await client.create_partition(collection)

    # Upload each chunk
    results = await client.upload_chunks(collection, chunks)

    return {
        "collection": collection,
        "strategy": strategy,
        "chunks_count": len(chunks),
        "results": results,
    }
