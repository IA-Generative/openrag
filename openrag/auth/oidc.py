"""OIDC/JWT authentication module for OpenRAG.

Validates JWT tokens issued by an OIDC provider (e.g. Keycloak),
extracts user identity and group claims, and syncs group memberships
to OpenRAG partitions.
"""

import hashlib
import os
import time
from dataclasses import dataclass, field

import httpx
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
from utils.logger import get_logger

logger = get_logger()

# --- Configuration from environment ---

OIDC_ISSUER_URL = os.getenv("OIDC_ISSUER_URL", "")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "")
OIDC_JWKS_CACHE_TTL = int(os.getenv("OIDC_JWKS_CACHE_TTL", "3600"))
OIDC_GROUP_CLAIM = os.getenv("OIDC_GROUP_CLAIM", "groups")
OIDC_AUTO_PROVISION = os.getenv("OIDC_AUTO_PROVISION", "true").lower() == "true"

# Group prefix → role mapping
OIDC_GROUP_PREFIX_VIEWER = os.getenv("OIDC_GROUP_PREFIX_VIEWER", "rag-query/")
OIDC_GROUP_PREFIX_EDITOR = os.getenv("OIDC_GROUP_PREFIX_EDITOR", "rag-edit/")
OIDC_GROUP_PREFIX_OWNER = os.getenv("OIDC_GROUP_PREFIX_OWNER", "rag-admin/")

# Sync mode: "additive" or "authoritative"
OIDC_GROUP_SYNC_MODE = os.getenv("OIDC_GROUP_SYNC_MODE", "additive")

ROLE_HIERARCHY = {"viewer": 1, "editor": 2, "owner": 3}

# Prefixes ordered from highest to lowest role so the highest role wins
GROUP_PREFIX_ROLE_MAP = [
    (OIDC_GROUP_PREFIX_OWNER, "owner"),
    (OIDC_GROUP_PREFIX_EDITOR, "editor"),
    (OIDC_GROUP_PREFIX_VIEWER, "viewer"),
]


# --- JWKS Cache ---

@dataclass
class _JWKSCache:
    keys: dict = field(default_factory=dict)
    fetched_at: float = 0.0

    @property
    def expired(self) -> bool:
        return (time.time() - self.fetched_at) > OIDC_JWKS_CACHE_TTL

    def clear(self):
        self.keys = {}
        self.fetched_at = 0.0


_jwks_cache = _JWKSCache()


async def _fetch_jwks() -> dict:
    """Fetch JWKS from the OIDC issuer's well-known endpoint."""
    if _jwks_cache.keys and not _jwks_cache.expired:
        return _jwks_cache.keys

    well_known_url = f"{OIDC_ISSUER_URL.rstrip('/')}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(well_known_url)
        resp.raise_for_status()
        oidc_config = resp.json()

        jwks_uri = oidc_config["jwks_uri"]
        resp = await client.get(jwks_uri)
        resp.raise_for_status()
        jwks = resp.json()

    _jwks_cache.keys = jwks
    _jwks_cache.fetched_at = time.time()
    return jwks


def clear_jwks_cache():
    """Clear the JWKS cache (useful for testing)."""
    _jwks_cache.clear()


# --- JWT Validation ---

@dataclass
class OIDCIdentity:
    """Parsed identity from a validated OIDC JWT."""

    sub: str
    email: str | None = None
    display_name: str | None = None
    groups: list[str] = field(default_factory=list)
    raw_claims: dict = field(default_factory=dict)


class OIDCValidationError(Exception):
    """Raised when JWT validation fails."""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def validate_jwt(token: str) -> OIDCIdentity:
    """Validate a JWT token and return the parsed identity.

    Raises OIDCValidationError on any validation failure.
    """
    try:
        jwks = await _fetch_jwks()
    except Exception as e:
        logger.error("Failed to fetch JWKS", error=str(e))
        raise OIDCValidationError(f"Failed to fetch JWKS: {e}", status_code=503)

    try:
        # Decode without verification first to get the header
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise OIDCValidationError(f"Invalid JWT header: {e}")

    # Find matching key
    kid = unverified_header.get("kid")
    rsa_key = None
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            rsa_key = key
            break

    if not rsa_key:
        # Key not found — maybe keys rotated. Clear cache and retry once.
        clear_jwks_cache()
        try:
            jwks = await _fetch_jwks()
        except Exception as e:
            raise OIDCValidationError(f"Failed to refresh JWKS: {e}", status_code=503)

        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = key
                break

    if not rsa_key:
        raise OIDCValidationError("No matching key found in JWKS for token kid")

    try:
        claims = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            audience=OIDC_AUDIENCE,
            issuer=OIDC_ISSUER_URL,
            options={"verify_at_hash": False},
        )
    except ExpiredSignatureError:
        raise OIDCValidationError("Token has expired")
    except JWTClaimsError as e:
        raise OIDCValidationError(f"Invalid token claims: {e}")
    except JWTError as e:
        raise OIDCValidationError(f"JWT validation failed: {e}")

    sub = claims.get("sub")
    if not sub:
        raise OIDCValidationError("Token missing 'sub' claim")

    # Extract display name from various possible claims
    display_name = claims.get("preferred_username") or claims.get("name") or claims.get("email")

    # Extract groups
    groups_raw = claims.get(OIDC_GROUP_CLAIM, [])
    if isinstance(groups_raw, str):
        groups_raw = [groups_raw]

    return OIDCIdentity(
        sub=sub,
        email=claims.get("email"),
        display_name=display_name,
        groups=groups_raw,
        raw_claims=claims,
    )


# --- Group → Partition Mapping ---

def parse_partition_roles(groups: list[str]) -> dict[str, str]:
    """Parse Keycloak groups into {partition_name: role} mapping.

    If a user belongs to multiple groups for the same partition,
    the highest role wins.

    Groups may have a leading '/' (Keycloak convention) which is stripped.
    """
    partition_roles: dict[str, str] = {}

    for group in groups:
        # Strip leading slash
        g = group.lstrip("/")

        for prefix, role in GROUP_PREFIX_ROLE_MAP:
            if g.startswith(prefix):
                partition = g[len(prefix):]
                if not partition:
                    continue
                existing_role = partition_roles.get(partition)
                if existing_role is None or ROLE_HIERARCHY[role] > ROLE_HIERARCHY[existing_role]:
                    partition_roles[partition] = role
                break

    return partition_roles


def _sync_cache_key(user_id: int, groups: list[str]) -> str:
    """Generate a cache key for group sync to avoid redundant DB operations."""
    groups_str = ",".join(sorted(groups))
    return hashlib.md5(f"{user_id}:{groups_str}".encode()).hexdigest()


# In-memory sync cache: {cache_key: expiry_timestamp}
_sync_cache: dict[str, float] = {}
_SYNC_CACHE_TTL = 60  # seconds


async def sync_user_memberships(
    partition_file_manager,
    user_id: int,
    groups: list[str],
    sync_mode: str | None = None,
) -> bool:
    """Sync Keycloak groups to PartitionMembership records.

    Args:
        partition_file_manager: The PartitionFileManager instance
        user_id: OpenRAG user ID
        groups: Raw group claims from JWT
        sync_mode: Override for OIDC_GROUP_SYNC_MODE

    Returns:
        True if sync was performed, False if cached/skipped
    """
    mode = sync_mode or OIDC_GROUP_SYNC_MODE

    # Check cache
    cache_key = _sync_cache_key(user_id, groups)
    now = time.time()
    if cache_key in _sync_cache and _sync_cache[cache_key] > now:
        return False

    # Clean expired entries periodically
    if len(_sync_cache) > 1000:
        expired = [k for k, v in _sync_cache.items() if v <= now]
        for k in expired:
            del _sync_cache[k]

    desired_roles = parse_partition_roles(groups)

    if mode == "authoritative":
        partition_file_manager.sync_oidc_memberships_authoritative(user_id, desired_roles)
    else:
        partition_file_manager.sync_oidc_memberships_additive(user_id, desired_roles)

    _sync_cache[cache_key] = now + _SYNC_CACHE_TTL
    return True


def clear_sync_cache():
    """Clear the sync cache (useful for testing)."""
    _sync_cache.clear()
