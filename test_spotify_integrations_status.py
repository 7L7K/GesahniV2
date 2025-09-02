#!/usr/bin/env python3
"""
Test for Spotify integrations status endpoint.
Tests the /v1/integrations/spotify/status endpoint functionality.
"""

import asyncio
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken
from app.auth_store import link_oauth_identity, ensure_tables


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    """Create temporary database for testing."""
    # Override auth store DB path
    original_auth_db = None
    try:
        import app.auth_store
        original_auth_db = app.auth_store.DB_PATH
        app.auth_store.DB_PATH = tmp_path / "test_auth.db"

        # Override token store DB path
        original_token_db = None
        import app.auth_store_tokens
        original_token_db = app.auth_store_tokens.DEFAULT_DB_PATH
        app.auth_store_tokens.DEFAULT_DB_PATH = str(tmp_path / "test_tokens.db")

        # Ensure tables exist
        await ensure_tables()

        # Create DAO
        token_db = tmp_path / "test_tokens.db"
        dao = TokenDAO(db_path=str(token_db))

        # Ensure token table exists
        await dao._ensure_table()

        yield dao

    finally:
        # Restore original paths
        try:
            if original_auth_db:
                app.auth_store.DB_PATH = original_auth_db
        except Exception:
            pass
        try:
            if original_token_db:
                app.auth_store_tokens.DEFAULT_DB_PATH = original_token_db
        except Exception:
            pass


@pytest_asyncio.fixture
async def create_test_identity(tmp_path):
    """Factory to create test identity."""
    async def _create_identity(user_id: str):
        identity_id = str(uuid.uuid4())
        provider_sub = f"spotify_sub_{int(time.time())}"

        await link_oauth_identity(
            id=identity_id,
            user_id=user_id,
            provider="spotify",
            provider_iss="https://accounts.spotify.com",
            provider_sub=provider_sub,
            email_normalized=f"user_{int(time.time())}@example.com",
            email_verified=True
        )
        return identity_id

    return _create_identity


@pytest.mark.asyncio
async def test_spotify_integrations_status_no_token(temp_db):
    """Test status endpoint when no token exists."""
    from app.api.spotify import integrations_spotify_status
    from fastapi import Request
    from unittest.mock import Mock
    from app.auth_store_tokens import get_token

    dao = temp_db

    async def mock_get_token(user_id, provider):
        return await dao.get_token(user_id, provider)

    # Create mock request
    request = Mock(spec=Request)

    # Call endpoint - should return not connected
    with patch('app.auth_store_tokens.get_token', side_effect=mock_get_token):
        result = await integrations_spotify_status(request, user_id="test_user_no_token")

    expected = {
        "connected": False,
        "expires_at": None,
        "last_refresh_at": None,
        "refreshed": False,
        "scopes": []
    }

    assert result == expected
    print("✅ Test passed: No token returns correct status")


@pytest.mark.asyncio
async def test_spotify_integrations_status_with_token(temp_db, create_test_identity):
    """Test status endpoint with a valid token."""
    from app.api.spotify import integrations_spotify_status
    from fastapi import Request
    from unittest.mock import Mock

    dao = temp_db

    # Create test identity and token
    user_id = "test_user_with_token"
    identity_id = await create_test_identity(user_id)

    # Create token
    now = int(time.time())
    token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=identity_id,
        access_token="B" + "A" * 17,  # Valid format
        refresh_token="A" + "B" * 17,  # Valid format
        scopes="user-read-email user-read-private",
        expires_at=now + 3600,  # Expires in 1 hour
        created_at=now - 3600,
        updated_at=now - 1800,  # Updated 30 minutes ago
        is_valid=True
    )

    # Store token
    result = await dao.upsert_token(token)
    assert result is True

    # Verify token was stored correctly
    stored_token = await dao.get_token(user_id, "spotify")
    print(f"Stored token: {stored_token}")
    assert stored_token is not None, "Token was not stored correctly"

    async def mock_get_token(user_id_arg, provider):
        result = await dao.get_token(user_id_arg, provider)
        print(f"Mock get_token called with user_id={user_id_arg}, provider={provider}, returning: {result}")
        return result

    # Create mock request
    request = Mock(spec=Request)

    # Call endpoint
    with patch('app.auth_store_tokens.get_token', side_effect=mock_get_token):
        status_result = await integrations_spotify_status(request, user_id=user_id)

    # Verify response
    assert status_result["connected"] is True
    assert status_result["expires_at"] == now + 3600
    assert status_result["last_refresh_at"] == 0  # No refresh yet (default value)
    assert status_result["refreshed"] is False
    assert status_result["scopes"] == ["user-read-email", "user-read-private"]

    print("✅ Test passed: Valid token returns correct status")


@pytest.mark.asyncio
async def test_spotify_integrations_status_expired_token(temp_db, create_test_identity):
    """Test status endpoint with an expired token."""
    from app.api.spotify import integrations_spotify_status
    from fastapi import Request
    from unittest.mock import Mock

    dao = temp_db

    # Create test identity and token
    user_id = "test_user_expired"
    identity_id = await create_test_identity(user_id)

    # Create expired token
    now = int(time.time())
    token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=identity_id,
        access_token="B" + "A" * 17,
        refresh_token="A" + "B" * 17,
        scopes="user-read-email",
        expires_at=now - 100,  # Expired 100 seconds ago
        created_at=now - 3600,
        updated_at=now - 1800,
        is_valid=True
    )

    # Try to store expired token - this should fail due to contract validation
    result = await dao.upsert_token(token)
    assert result is False  # Contract validation should prevent storing expired tokens

    # For this test, we'll simulate having an expired token by mocking get_token
    # to return an expired token
    async def mock_get_token(user_id_arg, provider):
        return ThirdPartyToken(
            user_id=user_id_arg,
            provider=provider,
            provider_iss="https://accounts.spotify.com",
            provider_sub="spotify_sub_123",
            identity_id=identity_id,
            access_token="B" + "A" * 17,
            refresh_token="A" + "B" * 17,
            scopes="user-read-email",
            expires_at=now - 100,  # Expired
            created_at=now - 3600,
            updated_at=now - 1800,
            last_refresh_at=0,
            is_valid=True
        )

    # Create mock request
    request = Mock(spec=Request)

    # Call endpoint
    with patch('app.auth_store_tokens.get_token', side_effect=mock_get_token):
        status_result = await integrations_spotify_status(request, user_id=user_id)

    # Verify response - should show not connected due to expiration
    assert status_result["connected"] is False
    assert status_result["expires_at"] == now - 100
    assert status_result["last_refresh_at"] == 0
    assert status_result["refreshed"] is False
    assert status_result["scopes"] == ["user-read-email"]

    print("✅ Test passed: Expired token returns not connected")


@pytest.mark.asyncio
async def test_spotify_integrations_status_recently_refreshed(temp_db, create_test_identity):
    """Test status endpoint with a recently refreshed token."""
    from app.api.spotify import integrations_spotify_status
    from fastapi import Request
    from unittest.mock import Mock

    dao = temp_db

    # Create test identity and token
    user_id = "test_user_refreshed"
    identity_id = await create_test_identity(user_id)

    # Create token with recent refresh
    now = int(time.time())
    token = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        provider_iss="https://accounts.spotify.com",
        provider_sub="spotify_sub_123",
        identity_id=identity_id,
        access_token="B" + "A" * 17,
        refresh_token="A" + "B" * 17,
        scopes="user-read-email",
        expires_at=now + 3600,
        created_at=now - 3600,
        updated_at=now - 1800,
        last_refresh_at=int(now - 1800),  # Refreshed 30 minutes ago
        refresh_error_count=0,
        is_valid=True
    )

    # For this test, we'll simulate having a recently refreshed token by mocking get_token
    async def mock_get_token(user_id_arg, provider):
        return ThirdPartyToken(
            user_id=user_id_arg,
            provider=provider,
            provider_iss="https://accounts.spotify.com",
            provider_sub="spotify_sub_123",
            identity_id="test_identity_123",
            access_token="B" + "A" * 17,
            refresh_token="A" + "B" * 17,
            scopes="user-read-email",
            expires_at=now + 3600,
            created_at=now - 3600,
            updated_at=now - 1800,
            last_refresh_at=int(now - 1800),  # Refreshed 30 minutes ago
            is_valid=True
        )

    # Create mock request
    request = Mock(spec=Request)

    # Call endpoint
    with patch('app.auth_store_tokens.get_token', side_effect=mock_get_token):
        status_result = await integrations_spotify_status(request, user_id=user_id)

    # Verify response
    assert status_result["connected"] is True
    assert status_result["expires_at"] == now + 3600
    assert status_result["last_refresh_at"] == int(now - 1800)
    assert status_result["refreshed"] is True  # Should be true (refreshed within last hour)
    assert status_result["scopes"] == ["user-read-email"]

    print("✅ Test passed: Recently refreshed token shows refreshed status")


if __name__ == "__main__":
    # Run tests manually
    import tempfile
    import os

    async def run_tests():
        with tempfile.TemporaryDirectory() as tmp_dir:
            auth_db_path = os.path.join(tmp_dir, "test_auth.db")
            token_db_path = os.path.join(tmp_dir, "test_tokens.db")

            # Override paths
            original_auth_db = None
            original_token_db = None
            try:
                import app.auth_store
                original_auth_db = app.auth_store.DB_PATH
                app.auth_store.DB_PATH = auth_db_path

                import app.auth_store_tokens
                original_token_db = app.auth_store_tokens.DEFAULT_DB_PATH
                app.auth_store_tokens.DEFAULT_DB_PATH = token_db_path

                # Initialize databases
                await ensure_tables()

                # Create DAO
                dao = TokenDAO(db_path=token_db_path)
                await dao._ensure_table()

                # Create test identity factory
                async def create_identity(user_id: str):
                    identity_id = str(uuid.uuid4())
                    provider_sub = f"spotify_sub_{int(time.time())}"

                    await link_oauth_identity(
                        id=identity_id,
                        user_id=user_id,
                        provider="spotify",
                        provider_iss="https://accounts.spotify.com",
                        provider_sub=provider_sub,
                        email_normalized=f"user_{int(time.time())}@example.com",
                        email_verified=True
                    )
                    return identity_id

                # Run tests
                await test_spotify_integrations_status_no_token(dao)
                await test_spotify_integrations_status_with_token(dao, create_identity)
                await test_spotify_integrations_status_expired_token(dao, create_identity)
                await test_spotify_integrations_status_recently_refreshed(dao, create_identity)

                print("\n🎉 All tests passed!")

            finally:
                # Restore original paths
                if original_auth_db:
                    app.auth_store.DB_PATH = original_auth_db
                if original_token_db:
                    app.auth_store_tokens.TokenDAO.DEFAULT_DB_PATH = original_token_db

    asyncio.run(run_tests())
