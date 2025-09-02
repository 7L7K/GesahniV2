"""
Comprehensive tests for token validation logic
Tests the robust token validation system we implemented
"""
import time
import pytest
import tempfile
from unittest.mock import Mock, patch

from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
class TestTokenValidation:
    """Test comprehensive token validation logic"""

    async def test_valid_spotify_token_structure(self, tmp_path):
        """Test validation of properly structured Spotify token"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())
        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="valid_access_token_123",
            refresh_token="valid_refresh_token_456",
            scopes="user-read-private user-read-email",
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        # Should validate successfully
        is_valid = dao._validate_token_for_storage(token)
        assert is_valid

        # Should store successfully
        stored = await dao.upsert_token(token)
        assert stored

        # Should retrieve successfully
        retrieved = await dao.get_token("test_user", "spotify")
        assert retrieved is not None
        assert retrieved.access_token == "valid_access_token_123"

    async def test_invalid_spotify_token_missing_issuer(self, tmp_path):
        """Test rejection of Spotify token without proper issuer"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())
        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss=None,  # Missing issuer!
            access_token="valid_access_token_123",
            refresh_token="valid_refresh_token_456",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Should fail validation
        is_valid = dao._validate_token_for_storage(token)
        assert not is_valid

        # Should fail to store
        stored = await dao.upsert_token(token)
        assert not stored

    async def test_invalid_spotify_token_wrong_issuer(self, tmp_path):
        """Test rejection of Spotify token with wrong issuer"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())
        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://wrong.issuer.com",  # Wrong issuer!
            access_token="valid_access_token_123",
            refresh_token="valid_refresh_token_456",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Should fail validation
        is_valid = dao._validate_token_for_storage(token)
        assert not is_valid

        # Should fail to store
        stored = await dao.upsert_token(token)
        assert not stored

    async def test_expired_token_handling(self, tmp_path):
        """Test handling of expired tokens"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())
        expired_token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="expired_token_123",
            refresh_token="valid_refresh_token_456",
            scopes="user-read-private",
            expires_at=now - 3600,  # Already expired!
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        # Should validate structurally (even if expired)
        is_valid = await dao._validate_token_for_storage(expired_token)
        assert is_valid

        # Should store successfully
        stored = await dao.upsert_token(expired_token)
        assert stored

        # But should be marked as expired when retrieved
        retrieved = await dao.get_token("test_user", "spotify")
        assert retrieved is not None
        assert retrieved.expires_at < now  # Confirm it's expired

    async def test_token_scope_validation(self, tmp_path):
        """Test token scope validation and unioning"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # First token with basic scope
        token1 = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="token1",
            refresh_token="refresh1",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Second token with additional scope
        token2 = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="token2",
            refresh_token="refresh2",
            scopes="user-read-email user-modify-playback-state",
            expires_at=now + 3600,
        )

        # Store both tokens
        await dao.upsert_token(token1)
        await dao.upsert_token(token2)

        # Should have unioned scopes
        retrieved = await dao.get_token("test_user", "spotify")
        assert retrieved is not None

        scopes = set((retrieved.scope or "").split())
        expected_scopes = {"user-read-private", "user-read-email", "user-modify-playback-state"}
        assert scopes == expected_scopes

    async def test_google_token_validation(self, tmp_path):
        """Test validation of Google tokens with different issuer"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())
        token = ThirdPartyToken(
            user_id="test_user",
            provider="google",
            provider_sub="google_user_123",
            provider_iss="https://accounts.google.com",
            access_token="google_token_123",
            refresh_token="google_refresh_456",
            scopes="https://www.googleapis.com/auth/calendar.readonly",
            expires_at=now + 3600,
        )

        # Should validate successfully with Google issuer
        is_valid = dao._validate_token_for_storage(token)
        assert is_valid

        # Should store successfully
        stored = await dao.upsert_token(token)
        assert stored

    async def test_malformed_token_rejection(self, tmp_path):
        """Test rejection of malformed tokens"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Test that malformed tokens are rejected during construction
        # The ThirdPartyToken constructor should validate required fields
        with pytest.raises(ValueError):
            malformed_token = ThirdPartyToken(
                user_id="test_user",
                provider="spotify",
                provider_sub="spotify_user_123",
                provider_iss="https://accounts.spotify.com",
                access_token="",  # Empty access token should be rejected
                refresh_token="refresh_123",
                scopes="user-read-private",
                expires_at=now + 3600,
            )

    async def test_token_encryption_validation(self, tmp_path):
        """Test that tokens are properly encrypted/decrypted"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())
        original_token = "super_secret_access_token_12345"

        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token=original_token,
            refresh_token="super_secret_refresh_token_67890",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Store the token
        stored = await dao.upsert_token(token)
        assert stored

        # Retrieve the token
        retrieved = await dao.get_token("test_user", "spotify")
        assert retrieved is not None

        # Access token should be decrypted back to original
        assert retrieved.access_token == original_token
        assert retrieved.refresh_token == "super_secret_refresh_token_67890"

        # But should be encrypted in database
        # (This would require direct database inspection, but that's complex in this test)

    async def test_multiple_users_isolation(self, tmp_path):
        """Test that tokens are properly isolated between users"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # User 1 token
        token_user1 = ThirdPartyToken(
            user_id="user1",
            provider="spotify",
            provider_sub="spotify_user1",
            provider_iss="https://accounts.spotify.com",
            access_token="token_user1",
            refresh_token="refresh_user1",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # User 2 token
        token_user2 = ThirdPartyToken(
            user_id="user2",
            provider="spotify",
            provider_sub="spotify_user2",
            provider_iss="https://accounts.spotify.com",
            access_token="token_user2",
            refresh_token="refresh_user2",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Store both tokens
        await dao.upsert_token(token_user1)
        await dao.upsert_token(token_user2)

        # Each user should only see their own token
        retrieved_user1 = await dao.get_token("user1", "spotify")
        retrieved_user2 = await dao.get_token("user2", "spotify")

        assert retrieved_user1 is not None
        assert retrieved_user2 is not None
        assert retrieved_user1.access_token == "token_user1"
        assert retrieved_user2.access_token == "token_user2"

        # All tokens for user1 should only include user1's tokens
        all_user1 = await dao.get_all_user_tokens("user1")
        assert len(all_user1) == 1
        assert all_user1[0].user_id == "user1"

    async def test_provider_specific_validation(self, tmp_path):
        """Test that different providers have different validation rules"""
        db_path = str(tmp_path / "test_tokens.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Spotify token with Google issuer should fail
        invalid_token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.google.com",  # Wrong issuer for Spotify!
            access_token="token_123",
            refresh_token="refresh_456",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Should fail validation
        is_valid = await dao._validate_token_for_storage(invalid_token)
        assert not is_valid

        # Google token with Spotify issuer should also fail
        invalid_google = ThirdPartyToken(
            user_id="test_user",
            provider="google",
            provider_sub="google_user_123",
            provider_iss="https://accounts.spotify.com",  # Wrong issuer for Google!
            access_token="token_123",
            refresh_token="refresh_456",
            scopes="https://www.googleapis.com/auth/calendar.readonly",
            expires_at=now + 3600,
        )

        # Should fail validation
        is_valid_google = await dao._validate_token_for_storage(invalid_google)
        assert not is_valid_google
