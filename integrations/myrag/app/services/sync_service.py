"""Sync service — synchronize Keycloak groups to OpenRAG memberships."""

import logging

from app.services.keycloak_client import KeycloakClient
from app.services.openrag_client import OpenRAGClient

logger = logging.getLogger("myrag.sync")


class SyncService:
    def __init__(
        self,
        keycloak_client: KeycloakClient | None = None,
        openrag_client: OpenRAGClient | None = None,
    ):
        self.kc = keycloak_client or KeycloakClient()
        self.openrag = openrag_client or OpenRAGClient()

    @staticmethod
    def _map_group_to_role(group_name: str) -> str:
        """Map a Keycloak group name to an OpenRAG role."""
        if group_name == "superadmin":
            return "superadmin"
        if group_name.endswith("-admin"):
            return "owner"
        return "editor"

    async def sync_collection(
        self,
        collection: str,
        user_group_id: str,
        admin_group_id: str | None = None,
    ) -> dict:
        """Sync a single collection's groups to OpenRAG memberships."""
        synced = 0
        errors = 0

        # Ensure partition exists
        await self.openrag.create_partition(collection)

        # Get existing OpenRAG users
        try:
            or_users = await self.openrag._get("/users/")
            or_users_list = or_users.get("users", []) if isinstance(or_users, dict) else or_users
            or_by_ext_id = {
                u.get("external_user_id"): u
                for u in or_users_list
                if u.get("external_user_id")
            }
        except Exception as e:
            logger.warning(f"Failed to list OpenRAG users: {e}")
            or_by_ext_id = {}

        # Sync user group members → editor role
        try:
            user_members = await self.kc.list_group_members(user_group_id)
        except Exception as e:
            logger.warning(f"Failed to list user group members: {e}")
            user_members = []

        for member in user_members:
            kc_id = member["id"]
            username = member.get("username", "")

            # Skip service accounts
            if username.startswith("service-account-"):
                continue

            or_user = or_by_ext_id.get(kc_id)
            if not or_user:
                # Create user in OpenRAG
                try:
                    display = (
                        f"{member.get('firstName', '')} {member.get('lastName', '')}".strip()
                        or username
                    )
                    or_user = await self.openrag._post(
                        "/users/",
                        json={
                            "display_name": display,
                            "external_user_id": kc_id,
                            "is_admin": False,
                        },
                    )
                    or_by_ext_id[kc_id] = or_user
                except Exception as e:
                    logger.warning(f"Failed to create user {username}: {e}")
                    errors += 1
                    continue

            # Add to partition as editor
            user_id = or_user.get("id")
            if user_id:
                try:
                    await self.openrag._upload_form(
                        f"/partition/{collection}/users",
                        data={"user_id": str(user_id), "role": "editor"},
                    )
                    synced += 1
                except Exception:
                    pass  # Already a member or other error

        # Sync admin group members → owner role
        if admin_group_id:
            try:
                admin_members = await self.kc.list_group_members(admin_group_id)
            except Exception:
                admin_members = []

            for member in admin_members:
                kc_id = member["id"]
                or_user = or_by_ext_id.get(kc_id)
                if or_user and or_user.get("id"):
                    try:
                        await self.openrag._upload_form(
                            f"/partition/{collection}/users",
                            data={"user_id": str(or_user["id"]), "role": "owner"},
                        )
                        synced += 1
                    except Exception:
                        pass

        return {
            "collection": collection,
            "synced": synced,
            "errors": errors,
        }

    async def sync_all(self) -> list[dict]:
        """Sync all MyRAG collection groups to OpenRAG."""
        collections = await self.kc.list_collection_groups()
        results = []

        for col in collections:
            try:
                result = await self.sync_collection(
                    collection=col["collection"],
                    user_group_id=col["user_group_id"],
                    admin_group_id=col.get("admin_group_id"),
                )
                results.append(result)
                logger.info(f"Synced {col['collection']}: {result['synced']} members")
            except Exception as e:
                logger.error(f"Failed to sync {col['collection']}: {e}")
                results.append({
                    "collection": col["collection"],
                    "synced": 0,
                    "errors": 1,
                    "error": str(e),
                })

        return results
