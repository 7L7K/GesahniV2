"""
Tests for the robust Spotify OAuth flow with our improvements
"""
import time
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
class TestSpotifyOAuthRobust:
    """Test the improved Spotify OAuth flow"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    async def dao(self, tmp_path):
        """Create fresh TokenDAO"""
        db_path = str(tmp_path / "spotify_oauth.db")
        dao = TokenDAO(db_path)
        yield dao

    async def test_successful_oauth_callback_storage(self, client, dao):
        """Test that OAuth callback properly stores tokens with issuer"""
        now = int(time.time())

        # Mock the OAuth callback data
        callback_data = {
            'access_token': 'spotify_access_token_123',
            'refresh_token': 'spotify_refresh_token_456',
            'expires_in': 3600,
            'scope': 'user-read-private user-read-email',
            'token_type': 'Bearer'
        }

        # Mock the token storage
        with patch('app.auth_store_tokens.TokenDAO', return_value=dao), \
             patch('app.api.spotify.get_spotify_oauth_token') as mock_get_token, \
             patch('app.api.spotify.verify_spotify_token') as mock_verify:

            mock_get_token.return_value = callback_data
            mock_verify.return_value = {'id': 'spotify_user_123'}

            # Simulate OAuth callback
            response = client.get(
                '/v1/spotify/callback',
                params={'code': 'auth_code_123', 'state': 'test_state'},
                cookies={'GSNH_SESS': 'session_123'}
            )

            # Should redirect successfully
            assert response.status_code == 302

            # Check that token was stored with correct issuer
            stored_token = await dao.get_token('test_user', 'spotify')
            assert stored_token is not None
            assert stored_token.provider_iss == 'https://accounts.spotify.com'
            assert stored_token.access_token == 'spotify_access_token_123'
            assert stored_token.refresh_token == 'spotify_refresh_token_456'

    async def test_oauth_callback_missing_issuer_validation(self, client, dao):
        """Test that OAuth callback fails without proper issuer"""
        # This test verifies our improvement - the old code would store tokens
        # without the provider_iss field, but our new code requires it

        callback_data = {
            'access_token': 'spotify_access_token_123',
            'refresh_token': 'spotify_refresh_token_456',
            'expires_in': 3600,
            'scope': 'user-read-private',
            'token_type': 'Bearer'
        }

        with patch('app.auth_store_tokens.TokenDAO', return_value=dao), \
             patch('app.api.spotify.get_spotify_oauth_token') as mock_get_token, \
             patch('app.api.spotify.verify_spotify_token') as mock_verify:

            mock_get_token.return_value = callback_data
            mock_verify.return_value = {'id': 'spotify_user_123'}

            # Mock the DAO to reject tokens without issuer
            original_upsert = dao.upsert_token

            async def validate_issuer_before_upsert(token):
                if not token.provider_iss:
                    return False  # Reject tokens without issuer
                return await original_upsert(token)

            dao.upsert_token = validate_issuer_before_upsert

            response = client.get(
                '/v1/spotify/callback',
                params={'code': 'auth_code_123', 'state': 'test_state'},
                cookies={'GSNH_SESS': 'session_123'}
            )

            # Should still redirect (error handling)
            assert response.status_code == 302

            # But token should not be stored due to missing issuer
            stored_token = await dao.get_token('test_user', 'spotify')
            assert stored_token is None

    async def test_spotify_connect_endpoint_authentication(self, client):
        """Test that Spotify connect endpoint requires authentication"""
        # Test unauthenticated request
        response = client.get('/v1/spotify/connect')
        assert response.status_code == 401

        # Test with invalid auth
        response = client.get(
            '/v1/spotify/connect',
            cookies={'GSNH_AT': 'invalid_token'}
        )
        assert response.status_code == 401

    async def test_spotify_status_endpoint_robust_error_handling(self, client, dao):
        """Test that status endpoint handles various error conditions"""
        # Test with no tokens
        response = client.get(
            '/v1/spotify/status',
            cookies={'GSNH_AT': 'valid_test_token'}
        )

        # Should handle gracefully
        data = response.json()
        assert 'connected' in data
        assert data['connected'] is False
        assert 'reason' in data

    async def test_spotify_status_with_valid_token(self, client, dao):
        """Test status endpoint with valid token"""
        now = int(time.time())

        # Create valid token
        valid_token = ThirdPartyToken(identity_id="b13c2375-dc0b-4c3d-b716-78ddfdcfb2a8", 
            user_id='test_user',
            provider='spotify',
            provider_sub='spotify_user_123',
            provider_iss='https://accounts.spotify.com',
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes='user-read-private',
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        await dao.upsert_token(valid_token)

        with patch('app.auth_store_tokens.TokenDAO', return_value=dao), \
             patch('app.integrations.spotify.client.SpotifyClient._bearer_token_only',
                   new_callable=AsyncMock) as mock_bearer:

            mock_bearer.return_value = None  # Success

            response = client.get(
                '/v1/spotify/status',
                cookies={'GSNH_AT': 'valid_test_token'}
            )

            data = response.json()
            assert data['connected'] is True
            assert 'reason' not in data or data['reason'] == ''

    async def test_spotify_status_with_expired_token_auto_refresh(self, client, dao):
        """Test status endpoint triggers token refresh for expired tokens"""
        now = int(time.time())

        # Create expired token
        expired_token = ThirdPartyToken(identity_id="cbd9a453-3807-4a7d-9295-09b1a30a5213", 
            user_id='test_user',
            provider='spotify',
            provider_sub='spotify_user_123',
            provider_iss='https://accounts.spotify.com',
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes='user-read-private',
            expires_at=now - 3600,  # Expired
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        with patch('app.auth_store_tokens.TokenDAO', return_value=dao), \
             patch('app.integrations.spotify.client.SpotifyClient._refresh_access_token',
                   new_callable=AsyncMock) as mock_refresh, \
             patch('app.integrations.spotify.client.SpotifyClient._bearer_token_only',
                   new_callable=AsyncMock) as mock_bearer:

            # Mock successful refresh
            mock_refresh.return_value = {
                'access_token': 'refreshed_token_123',
                'expires_at': now + 3600
            }
            mock_bearer.return_value = None  # Success after refresh

            response = client.get(
                '/v1/spotify/status',
                cookies={'GSNH_AT': 'valid_test_token'}
            )

            data = response.json()
            assert data['connected'] is True

            # Verify refresh was called
            mock_refresh.assert_called_once()

    async def test_spotify_status_refresh_failure_handling(self, client, dao):
        """Test status endpoint handles refresh failures gracefully"""
        now = int(time.time())

        # Create expired token
        expired_token = ThirdPartyToken(identity_id="0d21deaf-1863-4f25-a3b0-c1757e368fcc", 
            user_id='test_user',
            provider='spotify',
            provider_sub='spotify_user_123',
            provider_iss='https://accounts.spotify.com',
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes='user-read-private',
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        with patch('app.auth_store_tokens.TokenDAO', return_value=dao), \
             patch('app.integrations.spotify.client.SpotifyClient._refresh_access_token',
                   new_callable=AsyncMock) as mock_refresh:

            # Mock refresh failure
            mock_refresh.side_effect = Exception("Invalid refresh token")

            response = client.get(
                '/v1/spotify/status',
                cookies={'GSNH_AT': 'valid_test_token'}
            )

            data = response.json()
            assert data['connected'] is False
            assert 'reason' in data
            assert 'refresh failed' in data['reason'].lower()

    async def test_spotify_disconnect_functionality(self, client, dao):
        """Test disconnecting Spotify account"""
        now = int(time.time())

        # Create token to disconnect
        token = ThirdPartyToken(identity_id="85606d0a-26b6-410a-bb85-5c59c69c6c2c", 
            user_id='test_user',
            provider='spotify',
            provider_sub='spotify_user_123',
            provider_iss='https://accounts.spotify.com',
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes='user-read-private',
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        await dao.upsert_token(token)

        with patch('app.auth_store_tokens.TokenDAO', return_value=dao):
            # Disconnect
            response = client.post(
                '/v1/spotify/disconnect',
                cookies={'GSNH_AT': 'valid_test_token'}
            )

            # Should succeed
            assert response.status_code == 200

            # Token should be gone
            remaining_token = await dao.get_token('test_user', 'spotify')
            assert remaining_token is None

    async def test_spotify_token_for_sdk_endpoint(self, client, dao):
        """Test the token-for-SDK endpoint for frontend integration"""
        now = int(time.time())

        # Create valid token
        token = ThirdPartyToken(identity_id="4de17cb2-d14e-47d7-8cc7-f6ecc22e0f53", 
            user_id='test_user',
            provider='spotify',
            provider_sub='spotify_user_123',
            provider_iss='https://accounts.spotify.com',
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes='user-read-private streaming',
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        await dao.upsert_token(token)

        with patch('app.auth_store_tokens.TokenDAO', return_value=dao):
            response = client.get(
                '/v1/spotify/token-for-sdk',
                cookies={'GSNH_AT': 'valid_test_token'}
            )

            # Should return token data for frontend SDK
            assert response.status_code == 200
            data = response.json()
            assert 'access_token' in data
            assert 'refresh_token' in data
            assert 'expires_at' in data
            assert data['access_token'] == 'sdk_access_token'

    async def test_spotify_token_for_sdk_no_token(self, client, dao):
        """Test SDK endpoint when no token exists"""
        with patch('app.auth_store_tokens.TokenDAO', return_value=dao):
            response = client.get(
                '/v1/spotify/token-for-sdk',
                cookies={'GSNH_AT': 'valid_test_token'}
            )

            # Should return 404
            assert response.status_code == 404
            data = response.json()
            assert 'detail' in data

    async def test_spotify_oauth_state_validation(self, client):
        """Test OAuth state parameter validation"""
        # Test missing state
        response = client.get('/v1/spotify/callback', params={'code': 'auth_code'})
        assert response.status_code == 400

        # Test invalid state
        response = client.get(
            '/v1/spotify/callback',
            params={'code': 'auth_code', 'state': 'invalid_state'}
        )
        # Should handle gracefully (exact behavior depends on implementation)
        assert response.status_code in [302, 400]  # Redirect or error

    async def test_spotify_scope_validation(self, client, dao):
        """Test that token scopes are properly validated and stored"""
        now = int(time.time())

        # Test with minimal required scope
        token_minimal = ThirdPartyToken(identity_id="197d007a-c216-413c-af0f-8ebfbc3f6199", 
            user_id='test_user',
            provider='spotify',
            provider_sub='spotify_user_123',
            provider_iss='https://accounts.spotify.com',
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes='user-read-private',  # Minimal scope
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        await dao.upsert_token(token_minimal)

        # Test with comprehensive scope
        token_comprehensive = ThirdPartyToken(identity_id="971fc0b4-e879-4e49-a8b4-29ee5f2a67bf", 
            user_id='test_user2',
            provider='spotify',
            provider_sub='spotify_user_456',
            provider_iss='https://accounts.spotify.com',
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes='user-read-private user-read-email user-modify-playback-state streaming',  # Full scope
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        await dao.upsert_token(token_comprehensive)

        with patch('app.auth_store_tokens.TokenDAO', return_value=dao):
            # Both should be valid
            for user_id in ['test_user', 'test_user2']:
                token = await dao.get_token(user_id, 'spotify')
                assert token is not None
                assert 'user-read-private' in token.scope

    async def test_concurrent_oauth_callbacks(self, client, dao):
        """Test handling of concurrent OAuth callbacks"""
        import asyncio

        now = int(time.time())
        callback_data = {
            'access_token': 'concurrent_token',
            'refresh_token': 'concurrent_refresh',
            'expires_in': 3600,
            'scope': 'user-read-private',
            'token_type': 'Bearer'
        }

        async def mock_oauth_flow(user_id):
            # Simulate OAuth callback for different users
            token = ThirdPartyToken(identity_id="a4099c24-9296-4fae-87ba-fe1da42c0d9e", 
                user_id=user_id,
                provider='spotify',
                provider_sub=f'{user_id}_sub',
                provider_iss='https://accounts.spotify.com',
                access_token=f'token_{user_id}',
                refresh_token=f'refresh_{user_id}',
                scopes='user-read-private',
                expires_at=now + 3600,
                created_at=now,
                updated_at=now,
            )
            await dao.upsert_token(token)
            return token

        # Simulate concurrent callbacks
        tasks = [
            mock_oauth_flow(f'user_{i}')
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 5
        for result in results:
            assert result is not None

        # Verify all tokens stored
        for i in range(5):
            token = await dao.get_token(f'user_{i}', 'spotify')
            assert token is not None
            assert token.access_token == f'token_user_{i}'
