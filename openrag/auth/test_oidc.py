"""Tests for OIDC JWT validation and group parsing."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.oidc import (
    OIDCIdentity,
    OIDCValidationError,
    clear_jwks_cache,
    clear_sync_cache,
    parse_partition_roles,
    sync_user_memberships,
    validate_jwt,
)


# --- parse_partition_roles ---


class TestParsePartitionRoles:
    def test_basic_viewer(self):
        groups = ["/rag-query/finance"]
        assert parse_partition_roles(groups) == {"finance": "viewer"}

    def test_basic_editor(self):
        groups = ["rag-edit/legal"]
        assert parse_partition_roles(groups) == {"legal": "editor"}

    def test_basic_owner(self):
        groups = ["/rag-admin/hr"]
        assert parse_partition_roles(groups) == {"hr": "owner"}

    def test_highest_role_wins(self):
        groups = ["/rag-query/finance", "/rag-admin/finance", "/rag-edit/finance"]
        assert parse_partition_roles(groups) == {"finance": "owner"}

    def test_multiple_partitions(self):
        groups = ["/rag-query/finance", "/rag-edit/legal", "/rag-admin/hr"]
        assert parse_partition_roles(groups) == {
            "finance": "viewer",
            "legal": "editor",
            "hr": "owner",
        }

    def test_no_matching_groups(self):
        groups = ["/other-group", "random-group"]
        assert parse_partition_roles(groups) == {}

    def test_empty_groups(self):
        assert parse_partition_roles([]) == {}

    def test_no_leading_slash(self):
        groups = ["rag-query/data"]
        assert parse_partition_roles(groups) == {"data": "viewer"}

    def test_empty_partition_name_ignored(self):
        groups = ["/rag-query/"]
        assert parse_partition_roles(groups) == {}

    def test_mixed_valid_and_invalid(self):
        groups = ["/rag-query/finance", "/other-group", "rag-edit/legal"]
        assert parse_partition_roles(groups) == {"finance": "viewer", "legal": "editor"}


# --- validate_jwt ---


MOCK_JWKS = {
    "keys": [
        {
            "kid": "test-key-id",
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": "test-n",
            "e": "AQAB",
        }
    ]
}


class TestValidateJwt:
    @pytest.fixture(autouse=True)
    def setup(self):
        clear_jwks_cache()
        yield
        clear_jwks_cache()

    @pytest.mark.asyncio
    async def test_invalid_jwt_header(self):
        with pytest.raises(OIDCValidationError, match="Invalid JWT header"):
            await validate_jwt("not-a-jwt-token")

    @pytest.mark.asyncio
    async def test_jwks_fetch_failure(self):
        with patch("auth.oidc._fetch_jwks", side_effect=Exception("Network error")):
            with pytest.raises(OIDCValidationError, match="Failed to fetch JWKS"):
                await validate_jwt("eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LWlkIn0.eyJ0ZXN0IjoidmFsdWUifQ.signature")

    @pytest.mark.asyncio
    async def test_expired_token(self):
        """Test that an expired token raises the appropriate error."""
        # This would require a proper JWT — testing the error path
        with patch("auth.oidc._fetch_jwks", return_value=MOCK_JWKS):
            with patch("jose.jwt.decode", side_effect=__import__("jose.exceptions", fromlist=["ExpiredSignatureError"]).ExpiredSignatureError("Token expired")):
                with patch("jose.jwt.get_unverified_header", return_value={"kid": "test-key-id", "alg": "RS256"}):
                    with pytest.raises(OIDCValidationError, match="Token has expired"):
                        await validate_jwt("eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Qta2V5LWlkIn0.eyJ0ZXN0IjoidmFsdWUifQ.signature")

    @pytest.mark.asyncio
    async def test_valid_token_returns_identity(self):
        mock_claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "preferred_username": "testuser",
            "groups": ["/rag-query/finance", "/rag-edit/legal"],
        }
        with patch("auth.oidc._fetch_jwks", return_value=MOCK_JWKS):
            with patch("jose.jwt.get_unverified_header", return_value={"kid": "test-key-id", "alg": "RS256"}):
                with patch("jose.jwt.decode", return_value=mock_claims):
                    identity = await validate_jwt("fake.jwt.token")

        assert isinstance(identity, OIDCIdentity)
        assert identity.sub == "user-123"
        assert identity.email == "user@example.com"
        assert identity.display_name == "testuser"
        assert "/rag-query/finance" in identity.groups
        assert "/rag-edit/legal" in identity.groups

    @pytest.mark.asyncio
    async def test_missing_sub_claim(self):
        mock_claims = {"email": "user@example.com"}
        with patch("auth.oidc._fetch_jwks", return_value=MOCK_JWKS):
            with patch("jose.jwt.get_unverified_header", return_value={"kid": "test-key-id", "alg": "RS256"}):
                with patch("jose.jwt.decode", return_value=mock_claims):
                    with pytest.raises(OIDCValidationError, match="missing 'sub' claim"):
                        await validate_jwt("fake.jwt.token")

    @pytest.mark.asyncio
    async def test_no_matching_key_retries_jwks(self):
        """When kid doesn't match, should clear cache and retry."""
        empty_jwks = {"keys": []}
        call_count = 0

        async def mock_fetch():
            nonlocal call_count
            call_count += 1
            return empty_jwks

        with patch("auth.oidc._fetch_jwks", side_effect=mock_fetch):
            with patch("jose.jwt.get_unverified_header", return_value={"kid": "unknown-kid", "alg": "RS256"}):
                with pytest.raises(OIDCValidationError, match="No matching key"):
                    await validate_jwt("fake.jwt.token")

        # Should have tried fetching twice (initial + retry)
        assert call_count == 2


# --- sync_user_memberships ---


class TestSyncUserMemberships:
    @pytest.fixture(autouse=True)
    def setup(self):
        clear_sync_cache()
        yield
        clear_sync_cache()

    @pytest.mark.asyncio
    async def test_additive_sync_calls_correct_method(self):
        pfm = MagicMock()
        pfm.sync_oidc_memberships_additive = MagicMock()

        groups = ["/rag-query/finance"]
        result = await sync_user_memberships(pfm, user_id=1, groups=groups, sync_mode="additive")

        assert result is True
        pfm.sync_oidc_memberships_additive.assert_called_once_with(1, {"finance": "viewer"})

    @pytest.mark.asyncio
    async def test_authoritative_sync_calls_correct_method(self):
        pfm = MagicMock()
        pfm.sync_oidc_memberships_authoritative = MagicMock()

        groups = ["/rag-admin/hr"]
        result = await sync_user_memberships(pfm, user_id=2, groups=groups, sync_mode="authoritative")

        assert result is True
        pfm.sync_oidc_memberships_authoritative.assert_called_once_with(2, {"hr": "owner"})

    @pytest.mark.asyncio
    async def test_cache_prevents_duplicate_sync(self):
        pfm = MagicMock()
        pfm.sync_oidc_memberships_additive = MagicMock()

        groups = ["/rag-query/finance"]
        result1 = await sync_user_memberships(pfm, user_id=1, groups=groups, sync_mode="additive")
        result2 = await sync_user_memberships(pfm, user_id=1, groups=groups, sync_mode="additive")

        assert result1 is True
        assert result2 is False  # cached
        assert pfm.sync_oidc_memberships_additive.call_count == 1

    @pytest.mark.asyncio
    async def test_different_groups_not_cached(self):
        pfm = MagicMock()
        pfm.sync_oidc_memberships_additive = MagicMock()

        result1 = await sync_user_memberships(pfm, user_id=1, groups=["/rag-query/a"], sync_mode="additive")
        result2 = await sync_user_memberships(pfm, user_id=1, groups=["/rag-query/b"], sync_mode="additive")

        assert result1 is True
        assert result2 is True
        assert pfm.sync_oidc_memberships_additive.call_count == 2
