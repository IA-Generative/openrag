"""Keycloak Admin API client for MyRAG group management."""

import time

import httpx

from app.config import settings


class KeycloakClient:
    def __init__(
        self,
        base_url: str | None = None,
        realm: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        group_root: str | None = None,
        timeout: float = 15.0,
    ):
        self.base_url = (base_url or settings.keycloak_url).rstrip("/")
        self.realm = realm or settings.keycloak_realm
        self.client_id = client_id or settings.keycloak_client_id
        self.client_secret = client_secret or settings.keycloak_client_secret
        self.group_root = group_root or settings.myrag_group_root
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires: float = 0

    # --- Token management ---

    async def _post_form(self, url: str, data: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            return resp.json()

    async def _get_admin_token(self) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token

        # Try client_credentials first (service account)
        if self.client_secret:
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
            url = f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token"
            try:
                result = await self._post_form(url, data)
                self._token = result["access_token"]
                self._token_expires = time.time() + result.get("expires_in", 300) - 30
                return self._token
            except Exception:
                pass

        # Fallback: admin password on master realm
        admin_password = settings.keycloak_admin_password
        if admin_password:
            data = {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": settings.keycloak_admin_user,
                "password": admin_password,
            }
            url = f"{self.base_url}/realms/master/protocol/openid-connect/token"
            result = await self._post_form(url, data)
            self._token = result["access_token"]
            self._token_expires = time.time() + result.get("expires_in", 300) - 30
            return self._token

        raise RuntimeError("No Keycloak credentials configured (set KEYCLOAK_CLIENT_SECRET or KEYCLOAK_ADMIN_PASSWORD)")

    async def _admin_headers(self) -> dict:
        token = await self._get_admin_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # --- Low-level HTTP ---

    async def _admin_get(self, path: str, params: dict | None = None) -> list | dict:
        headers = await self._admin_headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/admin/realms/{self.realm}{path}",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _admin_post(self, path: str, json: dict | None = None) -> dict:
        headers = await self._admin_headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/admin/realms/{self.realm}{path}",
                headers=headers,
                json=json,
            )
            if resp.status_code == 409:
                return {"status": "exists"}
            resp.raise_for_status()
            if not resp.content:
                return {"status": "created"}
            return resp.json()

    async def _admin_put(self, path: str, json: dict | None = None) -> dict:
        headers = await self._admin_headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(
                f"{self.base_url}/admin/realms/{self.realm}{path}",
                headers=headers,
                json=json,
            )
            resp.raise_for_status()
            return {"status": "ok"}

    async def _admin_delete(self, path: str) -> dict:
        headers = await self._admin_headers()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(
                f"{self.base_url}/admin/realms/{self.realm}{path}",
                headers=headers,
            )
            resp.raise_for_status()
            return {"status": "deleted"}

    # --- Group operations ---

    async def _find_group_id(self, name: str, parent_id: str | None = None) -> str | None:
        """Find a group ID by name, optionally within a parent."""
        if parent_id:
            children = await self._admin_get(f"/groups/{parent_id}/children")
        else:
            children = await self._admin_get("/groups", params={"search": name, "exact": "true"})

        for g in children:
            if g.get("name") == name:
                return g["id"]
        return None

    async def _list_children(self, parent_id: str) -> list[dict]:
        """List all child groups of a parent group."""
        return await self._admin_get(f"/groups/{parent_id}/children")

    async def create_group(self, name: str, parent_id: str | None = None):
        """Create a group in Keycloak."""
        if parent_id:
            return await self._admin_post(f"/groups/{parent_id}/children", json={"name": name})
        return await self._admin_post("/groups", json={"name": name})

    async def list_group_members(self, group_id: str) -> list[dict]:
        """List members of a group."""
        return await self._admin_get(f"/groups/{group_id}/members")

    async def add_user_to_group(self, user_id: str, group_id: str):
        """Add a user to a group."""
        return await self._admin_put(f"/users/{user_id}/groups/{group_id}")

    async def remove_user_from_group(self, user_id: str, group_id: str):
        """Remove a user from a group."""
        return await self._admin_delete(f"/users/{user_id}/groups/{group_id}")

    async def list_users(self, max_results: int = 100) -> list[dict]:
        """List all users in the realm."""
        users = []
        first = 0
        while True:
            page = await self._admin_get("/users", params={"first": first, "max": max_results})
            if not page:
                break
            users.extend(page)
            if len(page) < max_results:
                break
            first += max_results
        return users

    async def get_user_groups(self, user_id: str) -> list[dict]:
        """Get groups for a specific user."""
        return await self._admin_get(f"/users/{user_id}/groups")

    # --- MyRAG-specific ---

    async def _ensure_root_group(self) -> str:
        """Ensure the MyRAG root group exists, return its ID."""
        root_name = self.group_root.strip("/").split("/")[0]
        root_id = await self._find_group_id(root_name)
        if not root_id:
            await self.create_group(root_name)
            root_id = await self._find_group_id(root_name)
        return root_id

    async def create_collection_groups(self, collection_name: str) -> dict:
        """Create the 2 groups for a collection: {collection} and {collection}-admin."""
        root_id = await self._ensure_root_group()

        # Create user group: myrag/{collection}
        await self.create_group(collection_name, parent_id=root_id)
        user_group_id = await self._find_group_id(collection_name, parent_id=root_id)

        # Create admin group: myrag/{collection}-admin
        admin_name = f"{collection_name}-admin"
        await self.create_group(admin_name, parent_id=root_id)
        admin_group_id = await self._find_group_id(admin_name, parent_id=root_id)

        return {
            "user_group_id": user_group_id,
            "admin_group_id": admin_group_id,
            "user_group_path": f"{self.group_root}/{collection_name}",
            "admin_group_path": f"{self.group_root}/{admin_name}",
        }

    async def delete_collection_groups(self, collection_name: str):
        """Delete the 2 groups for a collection."""
        root_id = await self._ensure_root_group()

        user_gid = await self._find_group_id(collection_name, parent_id=root_id)
        if user_gid:
            await self._admin_delete(f"/groups/{user_gid}")

        admin_gid = await self._find_group_id(f"{collection_name}-admin", parent_id=root_id)
        if admin_gid:
            await self._admin_delete(f"/groups/{admin_gid}")

    async def list_collection_groups(self) -> list[dict]:
        """List all MyRAG collection groups."""
        root_id = await self._ensure_root_group()
        children = await self._admin_get(f"/groups/{root_id}/children")

        collections = {}
        for g in children:
            name = g["name"]
            if name == "superadmin":
                continue
            if name.endswith("-admin"):
                base = name[:-6]
                collections.setdefault(base, {})["admin_group"] = g
            else:
                collections.setdefault(name, {})["user_group"] = g

        return [
            {
                "collection": name,
                "user_group_id": info.get("user_group", {}).get("id"),
                "admin_group_id": info.get("admin_group", {}).get("id"),
            }
            for name, info in sorted(collections.items())
        ]
