"""
Complete PAT (Personal Access Token) functionality tests.

This test demonstrates the full PAT lifecycle:
1. Creating PATs with SHA-256 hashing
2. Listing PATs for a user
3. Verifying PATs with async function
4. Revoking PATs
"""

import asyncio
import hashlib
import secrets
from unittest.mock import AsyncMock, patch

import pytest_asyncio

from app.api.auth import verify_pat_async
from app.auth_store import create_pat, get_pat_by_hash, list_pats_for_user, revoke_pat


class TestPATComplete:
    """Test complete PAT functionality."""

    @pytest_asyncio.fixture
    async def setup_user(self):
        """Set up test user and clean up after."""
        user_id = f"test_user_{secrets.token_hex(4)}"

        # Create test user in auth store
        from app.auth_store import create_user

        await create_user(id=user_id, email=f"{user_id}@test.com", name="Test User")

        yield user_id

        # Cleanup would happen here in real implementation

    async def test_pat_creation_and_hashing(self, setup_user):
        """Test PAT creation with proper SHA-256 hashing."""
        user_id = setup_user

        # Create a PAT
        pat_id = f"pat_{secrets.token_hex(4)}"
        token = f"pat_live_{secrets.token_urlsafe(24)}"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        await create_pat(
            id=pat_id,
            user_id=user_id,
            name="Test PAT",
            token_hash=token_hash,
            scopes=["read", "write"],
        )

        # Verify we can retrieve it by hash
        pat_record = await get_pat_by_hash(token_hash)
        assert pat_record is not None
        assert pat_record["id"] == pat_id
        assert pat_record["user_id"] == user_id
        assert pat_record["name"] == "Test PAT"
        assert pat_record["scopes"] == ["read", "write"]
        assert pat_record["revoked_at"] is None

        return token, pat_id

    async def test_verify_pat_async(self, setup_user):
        """Test async PAT verification."""
        user_id = setup_user
        token, pat_id = await self.test_pat_creation_and_hashing(setup_user)

        # Test valid token
        result = await verify_pat_async(token)
        assert result is not None
        assert result["id"] == pat_id
        assert result["user_id"] == user_id
        assert result["scopes"] == ["read", "write"]

        # Test invalid token
        result = await verify_pat_async("invalid-token")
        assert result is None

        # Test empty token
        result = await verify_pat_async("")
        assert result is None

        # Test token with insufficient scopes
        result = await verify_pat_async(token, ["admin"])
        assert result is None  # Should fail due to insufficient scopes

        # Test token with sufficient scopes
        result = await verify_pat_async(token, ["read"])
        assert result is not None  # Should succeed

        return token, pat_id

    async def test_list_pats_for_user(self, setup_user):
        """Test listing PATs for a user."""
        user_id = setup_user

        # Create multiple PATs
        pats = []
        for i in range(3):
            pat_id = f"pat_{secrets.token_hex(4)}"
            token = f"pat_live_{secrets.token_urlsafe(24)}"
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

            await create_pat(
                id=pat_id,
                user_id=user_id,
                name=f"Test PAT {i}",
                token_hash=token_hash,
                scopes=["read", "write"] if i % 2 == 0 else ["read"],
            )
            pats.append((token, pat_id))

        # List PATs for user
        user_pats = await list_pats_for_user(user_id)
        assert len(user_pats) == 3

        # Verify structure (no token hashes in listing)
        for pat in user_pats:
            assert "id" in pat
            assert "name" in pat
            assert "scopes" in pat
            assert "created_at" in pat
            assert "revoked_at" in pat
            # Should NOT contain token hash
            assert "token_hash" not in pat

        return pats

    async def test_revoke_pat(self, setup_user):
        """Test PAT revocation."""
        token, pat_id = await self.test_pat_creation_and_hashing(setup_user)

        # Verify token works before revocation
        result = await verify_pat_async(token)
        assert result is not None

        # Revoke the PAT
        await revoke_pat(pat_id)

        # Verify token no longer works
        result = await verify_pat_async(token)
        assert result is None  # Should be None due to revocation

        # Verify revoked_at is set
        pat_record = await get_pat_by_hash(
            hashlib.sha256(token.encode("utf-8")).hexdigest()
        )
        assert pat_record is not None
        assert pat_record["revoked_at"] is not None

    async def test_complete_pat_workflow(self, setup_user):
        """Test complete PAT workflow from creation to revocation."""
        user_id = setup_user

        # 1. Create PAT
        pat_id = f"pat_{secrets.token_hex(4)}"
        token = f"pat_live_{secrets.token_urlsafe(24)}"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        await create_pat(
            id=pat_id,
            user_id=user_id,
            name="Complete Test PAT",
            token_hash=token_hash,
            scopes=["read", "write", "admin"],
        )

        # 2. List PATs
        pats = await list_pats_for_user(user_id)
        assert len(pats) == 1
        assert pats[0]["id"] == pat_id
        assert pats[0]["name"] == "Complete Test PAT"
        assert pats[0]["scopes"] == ["read", "write", "admin"]
        assert pats[0]["revoked_at"] is None

        # 3. Verify token works
        result = await verify_pat_async(token)
        assert result is not None
        assert result["scopes"] == ["read", "write", "admin"]

        # 4. Test scope checking
        result = await verify_pat_async(token, ["read"])
        assert result is not None

        result = await verify_pat_async(token, ["nonexistent"])
        assert result is None

        # 5. Revoke PAT
        await revoke_pat(pat_id)

        # 6. Verify token no longer works
        result = await verify_pat_async(token)
        assert result is None

        # 7. Verify PAT appears as revoked in listing
        pats = await list_pats_for_user(user_id)
        assert len(pats) == 1
        assert pats[0]["revoked_at"] is not None

        print("✅ Complete PAT workflow test passed!")


# Integration test that would run with a real FastAPI test client
def test_pat_endpoints_integration():
    """Integration test for PAT endpoints (requires authentication setup)."""
    # This would be a full integration test with:
    # - Authenticated requests to /v1/pats endpoints
    # - Token verification in protected endpoints
    # - Error handling for invalid/revoked tokens
    pass


if __name__ == "__main__":
    # Run async tests
    async def run_tests():
        # Mock setup for standalone testing
        with patch("app.auth_store.ensure_tables", AsyncMock()):
            test_instance = TestPATComplete()

            # Run tests sequentially
            await test_instance.test_pat_creation_and_hashing("test_user_123")
            await test_instance.test_verify_pat_async("test_user_123")
            await test_instance.test_list_pats_for_user("test_user_123")
            await test_instance.test_revoke_pat("test_user_123")
            await test_instance.test_complete_pat_workflow("test_user_123")

    asyncio.run(run_tests())
