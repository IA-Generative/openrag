"""Collections router — CRUD for MyRAG collections."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.collection import CollectionConfig, DEFAULT_SYSTEM_PROMPT
from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/collections", tags=["Collections"])


class CreateCollectionRequest(BaseModel):
    name: str
    description: str = ""
    strategy: str = "auto"
    sensitivity: str = "public"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    graph_enabled: bool = False
    scope: str = "group"


class UpdateSystemPromptRequest(BaseModel):
    system_prompt: str


@router.get("")
async def list_collections():
    """List all MyRAG collections."""
    configs = CollectionConfig.list_all()
    return {"collections": [c.to_dict() for c in configs]}


@router.get("/{name}")
async def get_collection(name: str):
    """Get collection config."""
    config = CollectionConfig.load(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return config.to_dict()


@router.post("")
async def create_collection(req: CreateCollectionRequest):
    """Create a new collection — creates partition in OpenRAG + saves config."""
    existing = CollectionConfig.load(req.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Collection '{req.name}' already exists")

    # Create partition in OpenRAG
    client = OpenRAGClient()
    await client.create_partition(req.name)

    # Save config
    import time
    config = CollectionConfig(
        name=req.name,
        description=req.description,
        strategy=req.strategy,
        sensitivity=req.sensitivity,
        system_prompt=req.system_prompt,
        graph_enabled=req.graph_enabled,
        scope=req.scope,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    config.save()

    return {"status": "created", "collection": config.to_dict()}


@router.patch("/{name}/system-prompt")
async def update_system_prompt(name: str, req: UpdateSystemPromptRequest):
    """Update the system prompt for a collection."""
    config = CollectionConfig.load(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")

    config.system_prompt = req.system_prompt
    config.save()

    return {"status": "updated", "collection": name, "system_prompt": config.system_prompt}


@router.get("/{name}/system-prompt")
async def get_system_prompt(name: str):
    """Get the system prompt for a collection."""
    config = CollectionConfig.load(name)
    if not config:
        # Return default if collection exists in OpenRAG but not in MyRAG
        return {"collection": name, "system_prompt": DEFAULT_SYSTEM_PROMPT, "source": "default"}

    return {"collection": name, "system_prompt": config.system_prompt, "source": "collection"}
