#!/usr/bin/env python3
"""Sync Keycloak users and groups to OpenRAG — zero code modification.

This script reads users and groups from Keycloak's Admin API, then
provisions matching accounts and partition memberships in OpenRAG
via its REST API.

Usage:
    python sync_keycloak_openrag.py              # full sync
    python sync_keycloak_openrag.py --dry-run    # preview changes

Environment variables:
    KEYCLOAK_URL            Keycloak base URL (e.g. http://localhost:8082)
    KEYCLOAK_REALM          Realm name (default: openrag)
    KEYCLOAK_CLIENT_ID      Service-account client ID (default: openrag-sync)
    KEYCLOAK_CLIENT_SECRET  Service-account client secret
    OPENRAG_URL             OpenRAG API URL (e.g. http://localhost:8180)
    OPENRAG_ADMIN_TOKEN     Admin Bearer token for OpenRAG
    DRY_RUN                 Set to "true" for preview mode
    GROUP_PREFIX_VIEWER     Group prefix for viewer role (default: rag-query/)
    GROUP_PREFIX_EDITOR     Group prefix for editor role (default: rag-edit/)
    GROUP_PREFIX_OWNER      Group prefix for owner role (default: rag-admin/)
"""

import argparse
import logging
import os
import sys

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("sync")

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8082")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "openrag")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "openrag-sync")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")

OPENRAG_URL = os.getenv("OPENRAG_URL", "http://localhost:8180")
OPENRAG_ADMIN_TOKEN = os.getenv("OPENRAG_ADMIN_TOKEN", "")

GROUP_PREFIX_OWNER = os.getenv("GROUP_PREFIX_OWNER", "rag-admin/")
GROUP_PREFIX_EDITOR = os.getenv("GROUP_PREFIX_EDITOR", "rag-edit/")
GROUP_PREFIX_VIEWER = os.getenv("GROUP_PREFIX_VIEWER", "rag-query/")

GROUP_PREFIX_ROLE_MAP = [
    (GROUP_PREFIX_OWNER, "owner"),
    (GROUP_PREFIX_EDITOR, "editor"),
    (GROUP_PREFIX_VIEWER, "viewer"),
]

ROLE_HIERARCHY = {"viewer": 1, "editor": 2, "owner": 3}


def get_keycloak_token(client: httpx.Client) -> str:
    """Obtain an admin access token via client_credentials grant."""
    url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
    resp = client.post(
        url,
        data={
            "grant_type": "client_credentials",
            "client_id": KEYCLOAK_CLIENT_ID,
            "client_secret": KEYCLOAK_CLIENT_SECRET,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def list_keycloak_users(client: httpx.Client, token: str) -> list[dict]:
    """Fetch all users from Keycloak admin API (paginated)."""
    headers = {"Authorization": f"Bearer {token}"}
    users = []
    first = 0
    page_size = 100
    while True:
        url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"
        resp = client.get(url, headers=headers, params={"first": first, "max": page_size})
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        users.extend(page)
        if len(page) < page_size:
            break
        first += page_size
    return users


def get_user_groups(client: httpx.Client, token: str, user_id: str) -> list[str]:
    """Fetch groups for a specific Keycloak user."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/groups"
    resp = client.get(url, headers=headers)
    resp.raise_for_status()
    return [g["path"] for g in resp.json()]


def parse_partition_roles(groups: list[str]) -> dict[str, str]:
    """Parse Keycloak group paths into {partition: role} mapping.

    Same logic as openrag/auth/oidc.py:parse_partition_roles.
    """
    partition_roles: dict[str, str] = {}
    for group in groups:
        g = group.lstrip("/")
        for prefix, role in GROUP_PREFIX_ROLE_MAP:
            if g.startswith(prefix):
                partition = g[len(prefix):]
                if not partition:
                    continue
                existing = partition_roles.get(partition)
                if existing is None or ROLE_HIERARCHY[role] > ROLE_HIERARCHY[existing]:
                    partition_roles[partition] = role
                break
    return partition_roles


def list_openrag_users(client: httpx.Client) -> list[dict]:
    """List existing OpenRAG users."""
    headers = {"Authorization": f"Bearer {OPENRAG_ADMIN_TOKEN}"}
    resp = client.get(f"{OPENRAG_URL}/users/", headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("users", [])


def create_openrag_user(
    client: httpx.Client,
    display_name: str,
    external_user_id: str,
    dry_run: bool = False,
) -> dict | None:
    """Create a user in OpenRAG. Returns the created user dict."""
    if dry_run:
        log.info("  [DRY-RUN] Would create user: %s (%s)", display_name, external_user_id)
        return None
    headers = {
        "Authorization": f"Bearer {OPENRAG_ADMIN_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = client.post(
        f"{OPENRAG_URL}/users/",
        headers=headers,
        json={
            "display_name": display_name,
            "external_user_id": external_user_id,
            "is_admin": False,
        },
    )
    if resp.status_code == 409:
        log.info("  User already exists: %s", display_name)
        return None
    resp.raise_for_status()
    user = resp.json()
    log.info("  Created user: %s (id=%s, token=%s)", display_name, user["id"], user.get("token", "N/A"))
    return user


def ensure_partition(client: httpx.Client, partition: str, dry_run: bool = False) -> None:
    """Create partition if it doesn't exist."""
    if dry_run:
        log.info("  [DRY-RUN] Would ensure partition: %s", partition)
        return
    headers = {"Authorization": f"Bearer {OPENRAG_ADMIN_TOKEN}"}
    resp = client.post(f"{OPENRAG_URL}/partition/{partition}", headers=headers)
    if resp.status_code in (200, 201):
        log.info("  Created partition: %s", partition)
    elif resp.status_code == 409:
        pass  # already exists


def add_partition_member(
    client: httpx.Client,
    partition: str,
    user_id: int,
    role: str,
    dry_run: bool = False,
) -> None:
    """Add or update a user's membership in a partition."""
    if dry_run:
        log.info("  [DRY-RUN] Would add user %d to partition %s as %s", user_id, partition, role)
        return
    headers = {"Authorization": f"Bearer {OPENRAG_ADMIN_TOKEN}"}
    resp = client.post(
        f"{OPENRAG_URL}/partition/{partition}/users",
        headers=headers,
        json={"user_id": user_id, "role": role},
    )
    if resp.status_code in (200, 201):
        log.info("  Added user %d to %s as %s", user_id, partition, role)
    elif resp.status_code == 409:
        # Already a member — try to update role
        resp2 = client.patch(
            f"{OPENRAG_URL}/partition/{partition}/users/{user_id}",
            headers=headers,
            json={"role": role},
        )
        if resp2.is_success:
            log.info("  Updated user %d role in %s to %s", user_id, partition, role)


def sync(dry_run: bool = False) -> None:
    """Main sync logic."""
    with httpx.Client(timeout=30) as client:
        # 1. Get Keycloak admin token
        log.info("Authenticating to Keycloak at %s (realm: %s)...", KEYCLOAK_URL, KEYCLOAK_REALM)
        kc_token = get_keycloak_token(client)

        # 2. List Keycloak users
        kc_users = list_keycloak_users(client, kc_token)
        log.info("Found %d users in Keycloak", len(kc_users))

        # 3. List existing OpenRAG users (index by external_user_id)
        or_users = list_openrag_users(client)
        or_by_ext_id = {u.get("external_user_id"): u for u in or_users if u.get("external_user_id")}
        log.info("Found %d existing users in OpenRAG", len(or_users))

        created = 0
        memberships_added = 0

        for kc_user in kc_users:
            kc_id = kc_user["id"]
            username = kc_user.get("username", "")
            display_name = (
                f"{kc_user.get('firstName', '')} {kc_user.get('lastName', '')}".strip()
                or username
            )
            email = kc_user.get("email", "")

            # Skip service accounts
            if username.startswith("service-account-"):
                continue

            log.info("Processing: %s (sub=%s)", display_name, kc_id)

            # Get groups
            groups = get_user_groups(client, kc_token, kc_id)
            partition_roles = parse_partition_roles(groups)

            if not partition_roles:
                log.info("  No RAG groups assigned, skipping")
                continue

            # Find or create OpenRAG user
            or_user = or_by_ext_id.get(kc_id)
            if not or_user:
                or_user = create_openrag_user(client, display_name, kc_id, dry_run)
                if or_user:
                    created += 1
                    or_by_ext_id[kc_id] = or_user

            if not or_user and not dry_run:
                log.warning("  Could not find or create user, skipping memberships")
                continue

            user_id = or_user["id"] if or_user else 0

            # Sync partition memberships
            for partition, role in partition_roles.items():
                ensure_partition(client, partition, dry_run)
                add_partition_member(client, partition, user_id, role, dry_run)
                memberships_added += 1

        log.info(
            "Sync complete: %d users created, %d memberships added/updated%s",
            created,
            memberships_added,
            " (DRY-RUN)" if dry_run else "",
        )


def main():
    parser = argparse.ArgumentParser(description="Sync Keycloak users to OpenRAG")
    parser.add_argument("--dry-run", action="store_true", default=os.getenv("DRY_RUN", "").lower() == "true")
    args = parser.parse_args()

    if not KEYCLOAK_CLIENT_SECRET:
        log.error("KEYCLOAK_CLIENT_SECRET is required")
        sys.exit(1)
    if not OPENRAG_ADMIN_TOKEN:
        log.error("OPENRAG_ADMIN_TOKEN is required")
        sys.exit(1)

    sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
