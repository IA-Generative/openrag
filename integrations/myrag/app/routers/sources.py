"""Sources router — Legifrance source management + URL checking."""

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.legifrance_client import LegifranceClient, parse_legifrance_url

router = APIRouter(prefix="/api/sources", tags=["Sources"])


class AddSourceByUrlRequest(BaseModel):
    url: str
    collection: str
    refresh_mode: str = "manual"  # manual | daily | weekly


class AddSourceByIdRequest(BaseModel):
    type: str  # code | article | loi | jo
    legifrance_id: str
    collection: str
    scope: str = ""  # optional: partie_legislative, partie_reglementaire
    refresh_mode: str = "manual"


class SearchLegifranceRequest(BaseModel):
    query: str
    fond: str = "CODE_DATE"
    page_size: int = 10


@router.get("/check-url")
async def check_url(url: str = Query(..., description="URL to check")):
    """Check if a remote URL is accessible and return content info.

    Server-side HEAD request avoids browser CORS restrictions.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.head(url)
            if resp.status_code < 400:
                content_type = resp.headers.get("content-type", "inconnu").split(";")[0].strip()
                content_length = resp.headers.get("content-length")
                return {
                    "accessible": True,
                    "status_code": resp.status_code,
                    "content_type": content_type,
                    "content_length": int(content_length) if content_length else None,
                    "url": str(resp.url),  # final URL after redirects
                }
            return {
                "accessible": False,
                "status_code": resp.status_code,
                "content_type": None,
                "content_length": None,
            }
    except httpx.TimeoutException:
        return {"accessible": False, "error": "timeout"}
    except Exception as e:
        return {"accessible": False, "error": str(e)}


@router.get("/preview-url")
async def preview_url(
    url: str = Query(..., description="URL to preview"),
    max_chars: int = Query(4000, description="Max characters to return"),
):
    """Fetch the first bytes of a remote URL and return as text preview.

    Server-side fetch avoids CORS and X-Frame-Options restrictions.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    return {"content": None, "error": f"HTTP {resp.status_code}"}
                # Read only what we need
                chunks = []
                total = 0
                async for chunk in resp.aiter_text():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= max_chars:
                        break
                content = "".join(chunks)
                truncated = len(content) >= max_chars
                if truncated:
                    content = content[:max_chars]
                return {"content": content, "truncated": truncated}
    except httpx.TimeoutException:
        return {"content": None, "error": "timeout"}
    except Exception as e:
        return {"content": None, "error": str(e)}


@router.post("/legifrance/parse-url")
async def parse_url(req: AddSourceByUrlRequest):
    """Parse a Legifrance URL and extract the document type and ID."""
    result = parse_legifrance_url(req.url)
    if not result:
        raise HTTPException(status_code=400, detail="URL not recognized as a Legifrance URL")
    return {
        **result,
        "collection": req.collection,
        "refresh_mode": req.refresh_mode,
    }


@router.post("/legifrance/search")
async def search_legifrance(req: SearchLegifranceRequest):
    """Search Legifrance via PISTE API."""
    client = LegifranceClient()
    if not client.is_configured():
        raise HTTPException(status_code=503, detail="Legifrance PISTE credentials not configured")
    return await client.search(req.query, fond=req.fond, page_size=req.page_size)


@router.post("/legifrance/add")
async def add_source(req: AddSourceByIdRequest):
    """Add a Legifrance source to a collection.

    This registers the source for tracking. The actual fetch + indexation
    is triggered separately via POST /api/ingest/{collection}.
    """
    from app.services.collection_store import get_collection, update_collection

    config = await get_collection(req.collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{req.collection}' not found")

    await update_collection(req.collection, {
        "source_type": "legifrance",
        "source_url": req.legifrance_id,
    })

    return {
        "status": "registered",
        "collection": req.collection,
        "legifrance_id": req.legifrance_id,
        "type": req.type,
        "refresh_mode": req.refresh_mode,
    }


@router.get("/legifrance/status/{collection}")
async def source_status(collection: str):
    """Check the Legifrance source status for a collection."""
    from app.services.collection_store import get_collection

    config = await get_collection(collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")

    return {
        "collection": collection,
        "legifrance_source_id": config.get("source_url") or None,
        "source_type": config.get("source_type", ""),
        "configured": config.get("source_type") == "legifrance",
    }
