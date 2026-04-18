"""Sources router — Legifrance source management."""

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
    from app.models.collection import CollectionConfig

    config = CollectionConfig.load(req.collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{req.collection}' not found")

    config.legifrance_source_id = req.legifrance_id
    config.legifrance_refresh_mode = req.refresh_mode
    config.save()

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
    from app.models.collection import CollectionConfig

    config = CollectionConfig.load(collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")

    return {
        "collection": collection,
        "legifrance_source_id": config.legifrance_source_id or None,
        "refresh_mode": config.legifrance_refresh_mode,
        "configured": bool(config.legifrance_source_id),
    }
