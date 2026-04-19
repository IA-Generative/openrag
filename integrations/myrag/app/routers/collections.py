"""Collections router — CRUD for MyRAG collections + prompt templates."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.collection import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPLATE_KEY,
    get_prompt_template,
    list_prompt_templates,
    save_custom_template,
    delete_custom_template,
)
from app.services.collection_store import (
    list_collections as db_list_collections,
    get_collection as db_get_collection,
    create_collection as db_create_collection,
    update_collection as db_update_collection,
    get_system_prompt as db_get_system_prompt,
    update_system_prompt as db_update_system_prompt,
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
    system_prompt: str | None = None
    graph_enabled: bool = False
    ai_summary_enabled: bool = False
    ai_summary_threshold: int = 1000
    scope: str = "group"
    contact_name: str = ""
    contact_email: str = ""


class UpdateSystemPromptRequest(BaseModel):
    system_prompt: str


class CreateTemplateRequest(BaseModel):
    key: str
    name: str
    description: str = ""
    icon: str = "📄"
    prompt: str


# ============================================================
# Prompt templates catalog (MUST be before /{name} routes)
# ============================================================

@router.get("/templates", tags=["Prompt Templates"])
async def get_prompt_templates():
    return {"templates": list_prompt_templates()}


@router.get("/templates/{key}", tags=["Prompt Templates"])
async def get_prompt_template_detail(key: str):
    tpl = get_prompt_template(key)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{key}' not found")
    return {"key": key, **tpl}


@router.post("/templates", tags=["Prompt Templates"])
async def create_prompt_template(req: CreateTemplateRequest):
    existing = get_prompt_template(req.key)
    if existing and not existing.get("custom"):
        raise HTTPException(status_code=409, detail=f"Cannot overwrite builtin template '{req.key}'")
    save_custom_template(key=req.key, name=req.name, description=req.description, icon=req.icon, prompt=req.prompt)
    return {"status": "created", "key": req.key}


@router.put("/templates/{key}", tags=["Prompt Templates"])
async def update_prompt_template(key: str, req: CreateTemplateRequest):
    existing = get_prompt_template(key)
    if existing and not existing.get("custom"):
        raise HTTPException(status_code=403, detail=f"Cannot modify builtin template '{key}'")
    save_custom_template(key=key, name=req.name, description=req.description, icon=req.icon, prompt=req.prompt)
    return {"status": "updated", "key": key}


@router.delete("/templates/{key}", tags=["Prompt Templates"])
async def delete_prompt_template_endpoint(key: str):
    if not delete_custom_template(key):
        raise HTTPException(status_code=403, detail=f"Cannot delete builtin template '{key}'")
    return {"status": "deleted", "key": key}


# ============================================================
# Collection CRUD (backed by SQLite/PostgreSQL)
# ============================================================

@router.get("")
async def list_collections_endpoint():
    """List all MyRAG collections.

    Merges DB collections with OpenRAG partitions.
    """
    collections = await db_list_collections()
    known_names = {c["name"] for c in collections}

    # Also fetch partitions from OpenRAG
    try:
        client = OpenRAGClient(timeout=10.0)
        models = await client.list_models()
        for m in models.get("data", []):
            model_id = m.get("id", "")
            if model_id.startswith("openrag-"):
                name = model_id[len("openrag-"):]
                if name and name not in known_names and name not in ("all", "default"):
                    collections.append({"name": name, "description": "", "strategy": "auto",
                                        "sensitivity": "public", "scope": "group"})
                    known_names.add(name)

        # Enrich with file counts
        for c in collections:
            try:
                files = await client.list_files(c["name"])
                c["file_count"] = len(files)
                if not c.get("description") and files:
                    names = [f.get("original_filename") or f.get("filename", "") for f in files[:5]]
                    names = [n for n in names if n]
                    if names:
                        c["description"] = f"{len(files)} documents indexes ({', '.join(names[:3])}{'...' if len(files) > 3 else ''})"
            except Exception:
                c["file_count"] = 0
    except Exception:
        pass

    return {"collections": collections}


@router.post("")
async def create_collection_endpoint(req: CreateCollectionRequest):
    """Create a new collection."""
    existing = await db_get_collection(req.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Collection '{req.name}' already exists")

    system_prompt = req.system_prompt
    if not system_prompt:
        tpl = get_prompt_template(req.prompt_template)
        system_prompt = tpl["prompt"] if tpl else DEFAULT_SYSTEM_PROMPT

    # Create partition in OpenRAG
    client = OpenRAGClient()
    try:
        await client.create_partition(req.name)
    except Exception:
        pass  # OpenRAG may not be reachable

    data = req.model_dump()
    data["system_prompt"] = system_prompt
    collection = await db_create_collection(data)
    return {"status": "created", "collection": collection}


@router.get("/{name}")
async def get_collection_endpoint(name: str):
    collection = await db_get_collection(name)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return collection


@router.patch("/{name}")
async def update_collection_endpoint(name: str, updates: dict):
    collection = await db_update_collection(name, updates)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return collection


# --- System prompt ---

@router.get("/{name}/system-prompt")
async def get_system_prompt_endpoint(name: str):
    collection = await db_get_collection(name)
    if not collection:
        return {"collection": name, "system_prompt": DEFAULT_SYSTEM_PROMPT,
                "source": "default", "template": DEFAULT_TEMPLATE_KEY}
    return {
        "collection": name,
        "system_prompt": collection.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
        "source": "collection",
        "template": collection.get("prompt_template", DEFAULT_TEMPLATE_KEY),
    }


@router.patch("/{name}/system-prompt")
async def update_system_prompt_endpoint(name: str, req: UpdateSystemPromptRequest):
    result = await db_update_system_prompt(name, req.system_prompt)
    if not result:
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    return {"status": "updated", "collection": name, "system_prompt": result.get("system_prompt")}
