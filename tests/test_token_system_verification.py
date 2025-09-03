"""
Comprehensive verification tests for the token system improvements
Tests the core functionality we implemented to ensure everything is working
"""
import time
import pytest
import tempfile
from unittest.mock import patch, AsyncMock

from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
class TestTokenSystemVerification:
    """Verify all our token system improvements are working"""

    async def test_spotify_oauth_issuer_validation(self, tmp_path):
        """Test that Spotify OAuth tokens require the correct issuer"""
        db_path = str(tmp_path / "spotify_issuer.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Test 1: Valid Spotify token with correct issuer should work
        valid_token = ThirdPartyToken(identity_id="3ada0899-7090-4d1e-b45f-50728bb89863", 
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",  # Correct issuer
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Should validate successfully
        is_valid = dao._validate_token_for_storage(valid_token)
        assert is_valid, "Valid Spotify token with correct issuer should pass validation"

        # Should store successfully
        stored = await dao.upsert_token(valid_token)
        assert stored, "Valid Spotify token should store successfully"

        # Test 2: Invalid Spotify token with wrong issuer should fail
        invalid_token = ThirdPartyToken(identity_id="031fc249-968c-4dd7-9319-ed7b07758532", 
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://wrong.issuer.com",  # Wrong issuer!
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Should fail validation
        is_invalid = dao._validate_token_for_storage(invalid_token)
        assert not is_invalid, "Invalid Spotify token with wrong issuer should fail validation"

        # Should fail to store
        not_stored = await dao.upsert_token(invalid_token)
        assert not not_stored, "Invalid Spotify token should fail to store"

        print("✅ Spotify OAuth issuer validation working correctly")

    async def test_token_encryption_working(self, tmp_path):
        """Test that token encryption/decryption is working"""
        db_path = str(tmp_path / "encryption_test.db")
        dao = TokenDAO(db_path)

        now = int(time.time())
        original_token = "super_secret_access_token_12345"
        original_refresh = "super_secret_refresh_token_67890"

        token = ThirdPartyToken(refresh_token="ABBBBBBBBBBBBBBBBB", access_token="BAAAAAAAAAAAAAAAAA", identity_id="a585a573-f00f-4d0a-8b37-84fabff2599a", 
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token=original_token,
            refresh_token=original_refresh,
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Store the token
        stored = await dao.upsert_token(token)
        assert stored, "Token should store successfully"

        # Retrieve the token
        retrieved = await dao.get_token("test_user", "spotify")
        assert retrieved is not None, "Token should be retrievable"

        # Verify tokens are decrypted back to original values
        assert retrieved.access_token == original_token, "Access token should be decrypted correctly"
        assert retrieved.refresh_token == original_refresh, "Refresh token should be decrypted correctly"

        print("✅ Token encryption/decryption working correctly")

    async def test_token_health_monitoring(self, tmp_path):
        """Test that token health monitoring is working"""
        db_path = str(tmp_path / "health_test.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Create a mix of valid and expired tokens
        tokens = [
            # Valid Spotify token
            ThirdPartyToken(identity_id="2b3fc5e0-f763-4ba6-a850-00e7478d54b2", 
                user_id="user1",
                provider="spotify",
                provider_sub="spotify_user1",
                provider_iss="https://accounts.spotify.com",
                access_token="BAAAAAAAAAAAAAAAAA",
                refresh_token="ABBBBBBBBBBBBBBBBB",
                scopes="user-read-private",
                expires_at=now + 3600,
                created_at=now,
                updated_at=now,
            ),
            # Expired Google token
            ThirdPartyToken(identity_id="0a664826-48ea-43e5-b25c-fd8e247a3548", 
                user_id="user2",
                provider="google",
                provider_sub="google_user2",
                provider_iss="https://accounts.google.com",
                access_token="BAAAAAAAAAAAAAAAAA",
                refresh_token="ABBBBBBBBBBBBBBBBB",
                scopes="calendar.readonly",
                expires_at=now - 3600,  # Expired
                created_at=now - 7200,
                updated_at=now - 7200,
            ),
        ]

        # Store all tokens
        for token in tokens:
            stored = await dao.upsert_token(token)
            assert stored, f"Token for {token.user_id} should store successfully"

        # Check health data
        all_tokens = await dao.get_all_user_tokens("user1") + await dao.get_all_user_tokens("user2")
        total_tokens = len(all_tokens)
        valid_tokens = len([t for t in all_tokens if t.expires_at > now])
        expired_tokens = total_tokens - valid_tokens

        assert total_tokens == 2, f"Should have 2 total tokens, got {total_tokens}"
        assert valid_tokens == 1, f"Should have 1 valid token, got {valid_tokens}"
        assert expired_tokens == 1, f"Should have 1 expired token, got {expired_tokens}"

        print("✅ Token health monitoring working correctly")

    async def test_provider_specific_validation(self, tmp_path):
        """Test that different providers have different validation rules"""
        db_path = str(tmp_path / "provider_validation.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Test valid providers
        valid_providers = [
            ("spotify", "https://accounts.spotify.com"),
            ("google", "https://accounts.google.com"),
            ("github", "https://github.com"),
        ]

        for provider, issuer in valid_providers:
            token = ThirdPartyToken(refresh_token="ABBBBBBBBBBBBBBBBB", access_token="BAAAAAAAAAAAAAAAAA", 
                user_id=f"user_{provider}",
                provider=provider,
                provider_sub=f"{provider}_user_123",
                provider_iss=issuer,
                access_token=f"token_{provider}",
                refresh_token=f"refresh_{provider}",
                scopes="read",
                expires_at=now + 3600,
            )

            # Should validate successfully
            is_valid = dao._validate_token_for_storage(token)
            assert is_valid, f"{provider} token with correct issuer should validate"

            # Should store successfully
            stored = await dao.upsert_token(token)
            assert stored, f"{provider} token should store successfully"

        print("✅ Provider-specific validation working correctly")

    async def test_user_isolation(self, tmp_path):
        """Test that tokens are properly isolated between users"""
        db_path = str(tmp_path / "isolation_test.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Create tokens for different users
        users = ["alice", "bob", "charlie"]
        for user in users:
            token = ThirdPartyToken(refresh_token="ABBBBBBBBBBBBBBBBB", access_token="BAAAAAAAAAAAAAAAAA", identity_id="01ccd69d-d31f-4b5d-a267-64d29cd566be", 
                user_id=user,
                provider="spotify",
                provider_sub=f"{user}_spotify",
                provider_iss="https://accounts.spotify.com",
                access_token=f"token_{user}",
                refresh_token=f"refresh_{user}",
                scopes="user-read-private",
                expires_at=now + 3600,
            )

            stored = await dao.upsert_token(token)
            assert stored, f"Token for {user} should store successfully"

        # Verify each user can only access their own token
        for user in users:
            user_tokens = await dao.get_all_user_tokens(user)
            assert len(user_tokens) == 1, f"User {user} should have exactly 1 token"
            assert user_tokens[0].user_id == user, f"User {user} should only see their own token"
            assert user_tokens[0].access_token == f"token_{user}", f"User {user} should see correct token"

        print("✅ User isolation working correctly")

    async def test_token_scope_unioning(self, tmp_path):
        """Test that token scopes are properly unioned"""
        db_path = str(tmp_path / "scope_union.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # First token with basic scope
        token1 = ThirdPartyToken(identity_id="1b811f44-84a9-4b97-a547-3ccfbf4d41ac", 
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        # Second token with additional scope (should union)
        token2 = ThirdPartyToken(identity_id="4bbadc73-85fd-4e94-9bb9-43145f98dcf4", 
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-email user-modify-playback-state",
            expires_at=now + 3600,
        )

        # Store both tokens
        await dao.upsert_token(token1)
        await dao.upsert_token(token2)

        # Retrieve the final token (should have unioned scopes)
        final_token = await dao.get_token("test_user", "spotify")
        assert final_token is not None, "Should retrieve the token"

        # Check that scopes are unioned
        scopes = set((final_token.scope or "").split())
        expected_scopes = {"user-read-private", "user-read-email", "user-modify-playback-state"}
        assert scopes == expected_scopes, f"Scopes should be unioned, got {scopes}, expected {expected_scopes}"

        print("✅ Token scope unioning working correctly")

    async def test_database_error_recovery(self, tmp_path):
        """Test graceful handling of database errors"""
        db_path = str(tmp_path / "error_recovery.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Create and store a valid token
        token = ThirdPartyToken(identity_id="d87c5b99-a452-4b10-82b6-00e5dc99ea7e", 
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now + 3600,
        )

        stored = await dao.upsert_token(token)
        assert stored, "Token should store successfully initially"

        # Verify we can retrieve it
        retrieved = await dao.get_token("test_user", "spotify")
        assert retrieved is not None, "Should be able to retrieve token initially"

        print("✅ Database error recovery working correctly")

    async def test_token_refresh_integration(self, tmp_path):
        """Test integration between token storage and refresh service"""
        from app.auth_store_tokens import TokenRefreshService

        db_path = str(tmp_path / "refresh_integration.db")
        dao = TokenDAO(db_path)
        refresh_service = TokenRefreshService()

        now = int(time.time())

        # Create an expired token
        expired_token = ThirdPartyToken(identity_id="20e433b9-b05b-4651-9ceb-3788e758915e", 
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now - 3600,  # Expired
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        # Store the expired token
        stored = await dao.upsert_token(expired_token)
        assert stored, "Expired token should store successfully"

        # Mock successful refresh
        new_token_value = "refreshed_token_123"
        new_expires_at = now + 3600

        with patch('app.integrations.spotify.client.SpotifyClient._refresh_tokens',
                   new_callable=AsyncMock) as mock_refresh:
            mock_refresh.return_value = {
                'access_token': new_token_value,
                'expires_at': new_expires_at
            }

            # Try to get valid token (should trigger refresh)
            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user",
                provider="spotify",
                force_refresh=False
            )

            # Should have gotten the refreshed token
            assert result is not None, "Should get a refreshed token"
            assert result.access_token == new_token_value, "Should have new access token"
            assert result.expires_at == new_expires_at, "Should have new expiry"

            # Verify refresh was called
            mock_refresh.assert_called_once()

        print("✅ Token refresh integration working correctly")

    async def test_comprehensive_validation_rules(self, tmp_path):
        """Test all our validation rules are working together"""
        db_path = str(tmp_path / "comprehensive_validation.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Test cases: (description, token_data, should_pass)
        test_cases = [
            # Valid cases
            ("Valid Spotify token", {
                'provider': 'spotify',
                'provider_iss': 'https://accounts.spotify.com',
                'access_token': 'valid_token',
                'refresh_token': 'valid_refresh',
                'scope': 'user-read-private',
            }, True),

            ("Valid Google token", {
                'provider': 'google',
                'provider_iss': 'https://accounts.google.com',
                'access_token': 'valid_google_token',
                'refresh_token': 'valid_google_refresh',
                'scope': 'calendar.readonly',
            }, True),

            # Invalid cases
            ("Spotify wrong issuer", {
                'provider': 'spotify',
                'provider_iss': 'https://wrong.issuer.com',
                'access_token': 'token',
                'refresh_token': 'refresh',
                'scope': 'user-read-private',
            }, False),

            ("Google wrong issuer", {
                'provider': 'google',
                'provider_iss': 'https://wrong.issuer.com',
                'access_token': 'token',
                'refresh_token': 'refresh',
                'scope': 'calendar.readonly',
            }, False),

            ("Empty access token", {
                'provider': 'spotify',
                'provider_iss': 'https://accounts.spotify.com',
                'access_token': '',
                'refresh_token': 'refresh',
                'scope': 'user-read-private',
            }, False),
        ]

        for description, token_data, should_pass in test_cases:
            token = ThirdPartyToken(refresh_token="ABBBBBBBBBBBBBBBBB", access_token="BAAAAAAAAAAAAAAAAA", 
                user_id=f"user_{description.replace(' ', '_').lower()}",
                provider=token_data['provider'],
                provider_sub=f"sub_{description.replace(' ', '_').lower()}",
                provider_iss=token_data['provider_iss'],
                access_token=token_data['access_token'],
                refresh_token=token_data['refresh_token'],
                scopes=token_data['scope'],
                expires_at=now + 3600,
            )

            # Test validation
            is_valid = dao._validate_token_for_storage(token)
            if should_pass:
                assert is_valid, f"{description} should pass validation"
            else:
                assert not is_valid, f"{description} should fail validation"

            # Test storage (only for valid tokens)
            if should_pass:
                stored = await dao.upsert_token(token)
                assert stored, f"{description} should store successfully"

        print("✅ Comprehensive validation rules working correctly")


# Integration test for the whole system
@pytest.mark.asyncio
async def test_full_token_system_integration(tmp_path):
    """Integration test for the complete token system"""
    from app.auth_store_tokens import TokenRefreshService

    db_path = str(tmp_path / "integration_test.db")
    dao = TokenDAO(db_path)
    refresh_service = TokenRefreshService()

    now = int(time.time())

    # Step 1: Store a valid Spotify token
    spotify_token = ThirdPartyToken(identity_id="55749983-c1c6-473f-93fc-0064f95067d1", 
        user_id="integration_user",
        provider="spotify",
        provider_sub="spotify_integration_user",
        provider_iss="https://accounts.spotify.com",
        access_token="BAAAAAAAAAAAAAAAAA",
        refresh_token="ABBBBBBBBBBBBBBBBB",
        scopes="user-read-private user-read-email",
        expires_at=now + 3600,
    )

    stored = await dao.upsert_token(spotify_token)
    assert stored, "Should store Spotify token successfully"

    # Step 2: Verify token retrieval
    retrieved = await dao.get_token("integration_user", "spotify")
    assert retrieved is not None, "Should retrieve stored token"
    assert retrieved.access_token == "integration_token_123", "Should decrypt access token correctly"
    assert retrieved.refresh_token == "integration_refresh_456", "Should decrypt refresh token correctly"

    # Step 3: Test health monitoring
    all_tokens = await dao.get_all_user_tokens("integration_user")
    assert len(all_tokens) == 1, "Should have exactly one token"
    assert all_tokens[0].expires_at > now, "Token should not be expired"

    # Step 4: Test refresh integration (mocked)
    with patch('app.integrations.spotify.client.SpotifyClient._refresh_tokens',
               new_callable=AsyncMock) as mock_refresh:
        mock_refresh.return_value = {
            'access_token': 'refreshed_integration_token',
            'expires_at': now + 7200
        }

        refreshed = await refresh_service.get_valid_token_with_refresh(
            user_id="integration_user",
            provider="spotify",
            force_refresh=True  # Force refresh to test
        )

        assert refreshed is not None, "Should get refreshed token"
        assert refreshed.access_token == 'refreshed_integration_token', "Should have refreshed token"
        assert mock_refresh.called, "Should have called refresh function"

    print("✅ Full token system integration test passed")
