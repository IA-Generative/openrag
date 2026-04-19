"""Sync router — Keycloak ↔ OpenRAG synchronization."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.sync_service import SyncService

router = APIRouter(prefix="/api/sync", tags=["Sync"])


class CreateGroupRequest(BaseModel):
    name: str


@router.get("/groups")
async def list_keycloak_groups():
    """List MyRAG groups from Keycloak (under /myrag/ root).

    Returns groups with id, name and path. Useful for visibility configuration.
    """
    from app.services.keycloak_client import KeycloakClient

    kc = KeycloakClient()
    try:
        root_id = await kc._ensure_root_group()
        children = await kc._list_children(root_id)
        return [
            {"id": g["id"], "name": g["name"], "path": f"/myrag/{g['name']}"}
            for g in children
        ]
    except Exception as e:
        return []


@router.post("/create-group")
async def create_collection_group(req: CreateGroupRequest):
    """Create Keycloak groups for a collection under /myrag/.

    Creates both the user group (/myrag/{name}) and admin group (/myrag/{name}-admin).
    Compatible with keycloak-comu group management.
    """
    from app.services.keycloak_client import KeycloakClient

    kc = KeycloakClient()
    try:
        result = await kc.create_collection_groups(req.name)
        return {
            "status": "created",
            "groups": [
                f"/myrag/{req.name}",
                f"/myrag/{req.name}-admin",
            ],
            "detail": result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur Keycloak: {e}")


@router.post("")
async def sync_all():
    """Sync all MyRAG Keycloak groups to OpenRAG memberships."""
    service = SyncService()
    results = await service.sync_all()
    total_synced = sum(r.get("synced", 0) for r in results)
    total_errors = sum(r.get("errors", 0) for r in results)
    return {
        "status": "done",
        "collections_synced": len(results),
        "total_members_synced": total_synced,
        "total_errors": total_errors,
        "details": results,
    }


@router.post("/{collection}")
async def sync_collection(collection: str):
    """Sync a single collection's Keycloak groups to OpenRAG."""
    from app.services.keycloak_client import KeycloakClient

    kc = KeycloakClient()
    root_id = await kc._ensure_root_group()

    user_gid = await kc._find_group_id(collection, parent_id=root_id)
    admin_gid = await kc._find_group_id(f"{collection}-admin", parent_id=root_id)

    if not user_gid:
        return {"status": "error", "detail": f"Group myrag/{collection} not found in Keycloak"}

    service = SyncService(keycloak_client=kc)
    result = await service.sync_collection(
        collection=collection,
        user_group_id=user_gid,
        admin_group_id=admin_gid,
    )
    return result
