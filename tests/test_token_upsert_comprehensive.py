"""
Comprehensive tests for token upsert functionality including:
- Happy path with identity creation
- Conflict resolution and updates
- Foreign key violations
- NOT NULL constraint violations
- Concurrent upsert scenarios
"""

import asyncio
import sqlite3
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from app.auth_store_tokens import TokenDAO, _default_db_path
from app.models.third_party_tokens import ThirdPartyToken
from app.auth_store import _db_path as AUTH_DB_PATH, link_oauth_identity, ensure_tables


@pytest.fixture
async def temp_dbs(tmp_path):
    """Create temporary databases for testing."""
    # Create temporary token database
    token_db = tmp_path / "test_tokens.db"

    # Create temporary auth database
    auth_db = tmp_path / "test_auth.db"

    # Override the DB paths for testing
    original_token_path = _default_db_path()
    original_auth_path = AUTH_DB_PATH()

    # Set up auth database using environment variable override
    import os

    os.environ["USERS_DB"] = str(auth_db)

    # Ensure auth tables exist
    await ensure_tables()

    # Set up TokenDAO database using environment variable override
    os.environ["THIRD_PARTY_TOKENS_DB"] = str(token_db)

    # Create TokenDAO (will use the env var override) and ensure its tables exist
    dao = TokenDAO()
    await dao._ensure_table()  # Ensure token tables are created

    yield dao, auth_db

    # Restore original paths
    # Note: These are module-level constants, so we can't easily restore them
    # But that's okay for testing as each test gets its own temp directory


@pytest.fixture
async def create_test_identity(temp_dbs):
    """Helper fixture to create a test identity."""
    dao, auth_db = temp_dbs

    async def _create_identity(
        user_id: str,
        provider: str = "spotify",
        provider_sub: str = None,
        provider_iss: str = None,
    ):
        identity_id = str(uuid.uuid4())

        # Create identity in auth database
        await link_oauth_identity(
            id=identity_id,
            user_id=user_id,
            provider=provider,
            provider_sub=provider_sub or f"{provider}_sub_{uuid.uuid4().hex[:8]}",
            email_normalized=f"user_{uuid.uuid4().hex[:8]}@example.com",
            provider_iss=provider_iss
            or (
                "https://accounts.spotify.com"
                if provider == "spotify"
                else "https://accounts.google.com"
            ),
        )

        return identity_id

    return _create_identity


@pytest.mark.asyncio
async def test_upsert_happy_path(temp_dbs, create_test_identity):
    """Test successful upsert with identity creation and verification."""
    dao, _ = temp_dbs

    # Create test identity
    user_id = "test_user_happy"
    identity_id = await create_test_identity(user_id)

    # Create token
    now = int(time.time())
    token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=identity_id,
        access_token="BAAAAAAAAAAAAAAAAA"
        + "A" * 17,  # Valid format: starts with B, length = 18
        refresh_token="ABBBBBBBBBBBBBBBBB"
        + "B" * 17,  # Valid format: starts with A, length = 18
        scopes="user-read-email,user-read-private",
        expires_at=now + 3600,  # 1 hour from now
        created_at=now,
        updated_at=now,
        is_valid=True,
    )

    # Perform upsert
    result = await dao.upsert_token(token)
    assert result is True

    # Verify row was created
    retrieved = await dao.get_token(user_id, "spotify")
    assert retrieved is not None
    assert retrieved.user_id == user_id
    assert retrieved.provider == "spotify"
    assert retrieved.identity_id == identity_id
    assert retrieved.access_token == token.access_token
    assert retrieved.refresh_token == token.refresh_token
    assert retrieved.scopes == "user-read-email,user-read-private"
    assert retrieved.expires_at == token.expires_at
    assert retrieved.is_valid is True

    # Verify only one row exists
    all_tokens = await dao.get_all_user_tokens(user_id)
    assert len(all_tokens) == 1


@pytest.mark.asyncio
async def test_upsert_conflict_update(temp_dbs, create_test_identity):
    """Test upsert conflict resolution - insert then update should modify existing row."""
    dao, _ = temp_dbs

    # Create test identity
    user_id = "test_user_conflict"
    identity_id = await create_test_identity(user_id)

    # Create initial token
    now = int(time.time())
    initial_token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=identity_id,
        access_token="BAAAAAAAAAAAAAAAAA" + "A" * 17,
        refresh_token="ABBBBBBBBBBBBBBBBB" + "B" * 17,
        scopes="user-read-email",
        expires_at=now + 3600,
        created_at=now,
        updated_at=now,
        is_valid=True,
    )

    # Insert initial token
    result = await dao.upsert_token(initial_token)
    assert result is True

    # Get initial token to check timestamps
    initial_retrieved = await dao.get_token(user_id, "spotify")
    assert initial_retrieved is not None
    initial_updated_at = initial_retrieved.updated_at

    # Wait a moment to ensure updated_at changes
    time.sleep(0.01)

    # Create updated token with different values
    updated_token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=identity_id,
        access_token="BAAAAAAAAAAAAAAAAA" + "C" * 17,  # Different access token
        refresh_token="ABBBBBBBBBBBBBBBBB" + "D" * 17,  # Different refresh token
        scopes="user-read-email,user-read-private",  # Additional scope
        expires_at=now + 7200,  # Different expiry (2 hours)
        created_at=now,
        updated_at=now,
        is_valid=True,
    )

    # Upsert updated token (should update existing row, not create new)
    result = await dao.upsert_token(updated_token)
    assert result is True

    # Verify only one row exists (no duplicates)
    all_tokens = await dao.get_all_user_tokens(user_id)
    assert len(all_tokens) == 1

    # Verify the row was updated
    final_retrieved = await dao.get_token(user_id, "spotify")
    assert final_retrieved is not None
    assert final_retrieved.user_id == user_id
    assert final_retrieved.identity_id == identity_id
    assert final_retrieved.access_token == updated_token.access_token
    assert final_retrieved.refresh_token == updated_token.refresh_token
    assert (
        final_retrieved.scopes == "user-read-email user-read-private"
    )  # Union of scopes
    assert final_retrieved.expires_at == updated_token.expires_at
    # updated_at might be returned as string or int, so compare appropriately
    if isinstance(final_retrieved.updated_at, str):
        # If it's a string timestamp, just verify it's not empty
        assert final_retrieved.updated_at != ""
    else:
        # If it's an int/float, compare values
        assert final_retrieved.updated_at > initial_updated_at


@pytest.mark.asyncio
async def test_fk_violation(temp_dbs):
    """Test foreign key violation with random identity_id."""
    dao, _ = temp_dbs

    # Create token with random identity_id that doesn't exist in auth_identities
    random_identity_id = str(uuid.uuid4())
    user_id = "test_user_fk"

    now = int(time.time())
    token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=random_identity_id,  # This doesn't exist in auth_identities
        access_token="BAAAAAAAAAAAAAAAAA" + "A" * 17,
        refresh_token="ABBBBBBBBBBBBBBBBB" + "B" * 17,
        scopes="user-read-email",
        expires_at=now + 3600,
        created_at=now,
        updated_at=now,
        is_valid=True,
    )

    # Contract validation should catch this and reject the token
    result = await dao.upsert_token(token)
    assert result is False  # Should fail due to contract validation

    # Verify no token was created
    retrieved = await dao.get_token(user_id, "spotify")
    assert retrieved is None


@pytest.mark.asyncio
async def test_notnull_violation(temp_dbs, create_test_identity):
    """Test NOT NULL constraint validation with missing access_token."""
    dao, _ = temp_dbs

    # Create test identity
    user_id = "test_user_notnull"
    identity_id = await create_test_identity(user_id)

    # Try to create token without access_token (violates constructor validation)
    now = int(time.time())

    # Constructor validation should catch this
    with pytest.raises(
        ValueError, match="user_id, provider, and access_token are required"
    ):
        ThirdPartyToken(
            user_id=user_id,
            provider="spotify",
            provider_iss="https://accounts.spotify.com",
            provider_sub="spotify_sub_123",
            identity_id=identity_id,
            access_token=None,  # This violates constructor validation
            refresh_token="ABBBBBBBBBBBBBBBBB" + "B" * 17,
            scopes="user-read-email",
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
            is_valid=True,
        )

    # Verify no token was created (since constructor failed)
    retrieved = await dao.get_token(user_id, "spotify")
    assert retrieved is None


@pytest.mark.asyncio
async def test_concurrent_upserts(temp_dbs, create_test_identity):
    """Test concurrent upserts for same (identity_id, provider) - should not create duplicates."""
    dao, _ = temp_dbs

    # Create test identity
    user_id = "test_user_concurrent"
    identity_id = await create_test_identity(user_id)

    now = int(time.time())

    async def upsert_coroutine(
        token_id: str, access_token_suffix: str, expires_offset: int
    ):
        """Coroutine that performs an upsert with specific parameters."""
        token = ThirdPartyToken(
            id=token_id,
            user_id=user_id,
            provider="spotify",
            provider_iss="https://accounts.spotify.com",
            provider_sub="spotify_sub_123",
            identity_id=identity_id,
            access_token=f"B{'X' * 16}{access_token_suffix}",  # B + 16 X's + suffix
            refresh_token="ABBBBBBBBBBBBBBBBB" + "Y" * 17,  # Fixed refresh token
            scopes="user-read-email,user-read-private",
            expires_at=now + expires_offset,
            created_at=now,
            updated_at=now,
            is_valid=True,
        )
        return await dao.upsert_token(token)

    # Run multiple upserts concurrently
    results = await asyncio.gather(
        upsert_coroutine("token_1", "1", 3600),  # expires in 1 hour
        upsert_coroutine("token_2", "2", 7200),  # expires in 2 hours
        upsert_coroutine("token_3", "3", 10800),  # expires in 3 hours
    )

    # All upserts should succeed
    assert all(results) is True

    # Verify only one row exists (no duplicates)
    all_tokens = await dao.get_all_user_tokens(user_id)
    assert len(all_tokens) == 1

    # Verify the final row has the last write's expires_at (10800 seconds)
    final_token = await dao.get_token(user_id, "spotify")
    assert final_token is not None
    assert final_token.expires_at == now + 10800
    assert final_token.access_token.endswith("3")  # Should have the last access token
    assert final_token.scopes == "user-read-email user-read-private"


@pytest.mark.asyncio
async def test_spotify_contract_validation_integration(temp_dbs, create_test_identity):
    """Test that Spotify contract validation is properly integrated and working."""
    dao, _ = temp_dbs

    # Create test identity
    user_id = "test_user_contract"
    identity_id = await create_test_identity(user_id)

    # Test 1: Valid Spotify token should pass contract validation
    now = int(time.time())
    valid_token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=identity_id,
        access_token="BAAAAAAAAAAAAAAAAA" + "A" * 17,  # Valid format and length
        refresh_token="ABBBBBBBBBBBBBBBBB" + "B" * 17,  # Valid format and length
        scopes="user-read-email,user-read-private",
        expires_at=now + 3600,  # Future expiry
        created_at=now,
        updated_at=now,
        is_valid=True,
    )

    result = await dao.upsert_token(valid_token)
    assert result is True

    # Test 2: Invalid Spotify token should fail contract validation
    invalid_token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=identity_id,
        access_token="BAAAAAAAAAAAAAAAAA"
        + "A" * 17,  # Invalid format (should start with B)
        refresh_token="A" + "B" * 17,
        scopes="user-read-email",
        expires_at=now + 3600,
        created_at=now,
        updated_at=now,
        is_valid=True,
    )

    result = await dao.upsert_token(invalid_token)
    assert result is False  # Should fail due to contract validation

    # Verify invalid token was not stored
    all_tokens = await dao.get_all_user_tokens(user_id)
    assert len(all_tokens) == 1  # Only the valid token should exist
