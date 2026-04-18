"""Collections router — CRUD for MyRAG collections + prompt templates."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.collection import (
    CollectionConfig,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPLATE_KEY,
    PROMPT_TEMPLATES,
    get_prompt_template,
    list_prompt_templates,
    save_custom_template,
    delete_custom_template,
)
from app.services.openrag_client import OpenRAGClient

router = APIRouter(prefix="/api/collections", tags=["Collections"])


# --- Request models ---

class CreateCollectionRequest(BaseModel):
    name: str
    description: str = ""
    strategy: str = "auto"
    sensitivity: str = "public"
    prompt_template: str = DEFAULT_TEMPLATE_KEY
    system_prompt: str | None = None  # if None, use the template's prompt
    graph_enabled: bool = False
    scope: str = "group"


class UpdateSystemPromptRequest(BaseModel):
    system_prompt: str


class CreateTemplateRequest(BaseModel):
    key: str
    name: str
    description: str = ""
    icon: str = "📄"
    prompt: str


# --- Collection CRUD ---

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

    # Resolve system prompt from template if not provided
    system_prompt = req.system_prompt
    if not system_prompt:
        tpl = get_prompt_template(req.prompt_template)
        if tpl:
            system_prompt = tpl["prompt"]
        else:
            system_prompt = DEFAULT_SYSTEM_PROMPT

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
        prompt_template=req.prompt_template,
        system_prompt=system_prompt,
        graph_enabled=req.graph_enabled,
        scope=req.scope,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    config.save()

    return {"status": "created", "collection": config.to_dict()}


# --- System prompt ---

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
        return {"collection": name, "system_prompt": DEFAULT_SYSTEM_PROMPT,
                "source": "default", "template": DEFAULT_TEMPLATE_KEY}

    return {
        "collection": name,
        "system_prompt": config.system_prompt,
        "source": "collection",
        "template": config.prompt_template,
    }


# --- Prompt templates catalog ---

@router.get("/_templates", tags=["Prompt Templates"])
async def get_prompt_templates():
    """List all available prompt templates (builtin + custom)."""
    return {"templates": list_prompt_templates()}


@router.get("/_templates/{key}", tags=["Prompt Templates"])
async def get_prompt_template_detail(key: str):
    """Get a prompt template with its full prompt text."""
    tpl = get_prompt_template(key)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{key}' not found")
    return {"key": key, **tpl}


@router.post("/_templates", tags=["Prompt Templates"])
async def create_prompt_template(req: CreateTemplateRequest):
    """Create a custom prompt template (admin). Cannot overwrite builtins."""
    existing = get_prompt_template(req.key)
    if existing and not existing.get("custom"):
        raise HTTPException(status_code=409, detail=f"Cannot overwrite builtin template '{req.key}'")

    save_custom_template(
        key=req.key,
        name=req.name,
        description=req.description,
        icon=req.icon,
        prompt=req.prompt,
    )
    return {"status": "created", "key": req.key}


@router.put("/_templates/{key}", tags=["Prompt Templates"])
async def update_prompt_template(key: str, req: CreateTemplateRequest):
    """Update a custom prompt template. Cannot modify builtins."""
    existing = get_prompt_template(key)
    if existing and not existing.get("custom"):
        raise HTTPException(status_code=403, detail=f"Cannot modify builtin template '{key}'")

    save_custom_template(
        key=key,
        name=req.name,
        description=req.description,
        icon=req.icon,
        prompt=req.prompt,
    )
    return {"status": "updated", "key": key}


@router.delete("/_templates/{key}", tags=["Prompt Templates"])
async def delete_prompt_template_endpoint(key: str):
    """Delete a custom prompt template. Cannot delete builtins."""
    if not delete_custom_template(key):
        raise HTTPException(status_code=403, detail=f"Cannot delete builtin template '{key}'")
    return {"status": "deleted", "key": key}
