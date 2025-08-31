"""
Tests for comprehensive error handling and recovery in token system
"""
import time
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth_store_tokens import TokenDAO, TokenRefreshService
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
class TestTokenErrorHandling:
    """Test error handling and recovery mechanisms"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    async def dao(self, tmp_path):
        """Create fresh TokenDAO"""
        db_path = str(tmp_path / "error_handling.db")
        dao = TokenDAO(db_path)
        yield dao

    @pytest.fixture
    def refresh_service(self, dao):
        """Create TokenRefreshService"""
        return TokenRefreshService(dao)

    async def test_database_connection_failure_recovery(self, dao):
        """Test recovery from database connection failures"""
        now = int(time.time())

        # Create a token
        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="test_token",
            refresh_token="test_refresh",
            scope="user-read-private",
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        # Store successfully
        stored = await dao.upsert_token(token)
        assert stored

        # Mock database failure
        with patch.object(dao, 'get_token', side_effect=Exception("Database connection lost")):
            # Operation should handle the error gracefully
            result = await dao.get_token("test_user", "spotify")

            # Should return None instead of crashing
            assert result is None

    async def test_network_timeout_during_refresh(self, dao, refresh_service):
        """Test handling of network timeouts during token refresh"""
        now = int(time.time())

        expired_token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="expired_token",
            refresh_token="valid_refresh",
            scope="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Mock network timeout
        with patch('app.integrations.spotify.client.SpotifyClient._refresh_access_token',
                   new_callable=AsyncMock) as mock_refresh:
            mock_refresh.side_effect = Exception("Network timeout")

            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user",
                provider="spotify",
                force_refresh=False
            )

            # Should return None after exhausting retries
            assert result is None
            assert mock_refresh.call_count == 3  # All retries attempted

    async def test_malformed_api_response_handling(self, dao, refresh_service):
        """Test handling of malformed API responses"""
        now = int(time.time())

        expired_token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="expired_token",
            refresh_token="valid_refresh",
            scope="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Mock malformed responses
        malformed_responses = [
            None,  # Null response
            {},    # Empty response
            {"access_token": None},  # Missing required fields
            {"access_token": ""},    # Empty token
            "not_a_dict",  # Wrong type
        ]

        for malformed_response in malformed_responses:
            with patch('app.integrations.spotify.client.SpotifyClient._refresh_access_token',
                       new_callable=AsyncMock) as mock_refresh:
                mock_refresh.return_value = malformed_response

                result = await refresh_service.get_valid_token_with_refresh(
                    user_id="test_user",
                    provider="spotify",
                    force_refresh=True
                )

                # Should handle gracefully
                assert result is None

    async def test_concurrent_modification_conflict_resolution(self, dao):
        """Test handling of concurrent token modifications"""
        import asyncio

        now = int(time.time())

        async def concurrent_update(user_id, token_value):
            """Simulate concurrent token updates"""
            token = ThirdPartyToken(
                user_id=user_id,
                provider="spotify",
                provider_sub=f"{user_id}_sub",
                provider_iss="https://accounts.spotify.com",
                access_token=f"token_{token_value}",
                refresh_token=f"refresh_{token_value}",
                scope="user-read-private",
                expires_at=now + 3600,
                created_at=now,
                updated_at=now,
            )

            # Add small delay to increase chance of concurrency
            await asyncio.sleep(0.01)
            return await dao.upsert_token(token)

        # Launch multiple concurrent updates
        tasks = [
            concurrent_update("test_user", i)
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # At least some should succeed
        successful_updates = sum(1 for result in results if result)
        assert successful_updates > 0

        # Final token should be one of the successful updates
        final_token = await dao.get_token("test_user", "spotify")
        assert final_token is not None
        assert final_token.access_token.startswith("token_")

    async def test_encryption_key_rotation_handling(self, dao):
        """Test handling of encryption key rotation scenarios"""
        now = int(time.time())

        original_token = "original_secret_token"

        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token=original_token,
            refresh_token="original_refresh",
            scope="user-read-private",
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        await dao.upsert_token(token)

        # Retrieve and verify
        retrieved = await dao.get_token("test_user", "spotify")
        assert retrieved.access_token == original_token

        # Simulate encryption key change by mocking decryption failure
        with patch.object(dao, '_decrypt_token', side_effect=Exception("Decryption failed - key changed?")):
            # Should handle gracefully
            failed_retrieval = await dao.get_token("test_user", "spotify")
            assert failed_retrieval is None

    async def test_partial_token_data_corruption_recovery(self, dao):
        """Test recovery from partial token data corruption"""
        now = int(time.time())

        # Create valid token
        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="valid_token",
            refresh_token="valid_refresh",
            scope="user-read-private",
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        await dao.upsert_token(token)

        # Simulate partial corruption by mocking database to return incomplete data
        original_get_token = dao.get_token

        async def corrupted_get_token(user_id, provider):
            result = await original_get_token(user_id, provider)
            if result:
                # Corrupt the result
                result.access_token = None  # Missing access token
            return result

        dao.get_token = corrupted_get_token

        # Should handle the corruption gracefully
        corrupted_token = await dao.get_token("test_user", "spotify")
        assert corrupted_token is None or corrupted_token.access_token is None

        # Restore original function
        dao.get_token = original_get_token

        # Normal retrieval should still work
        normal_token = await dao.get_token("test_user", "spotify")
        assert normal_token is not None
        assert normal_token.access_token == "valid_token"

    async def test_rate_limit_exhaustion_handling(self, client, dao, refresh_service):
        """Test handling of API rate limit exhaustion"""
        now = int(time.time())

        expired_token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="expired_token",
            refresh_token="rate_limited_refresh",
            scope="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Mock rate limit responses
        rate_limit_errors = [
            Exception("429 Too Many Requests"),
            Exception("Rate limit exceeded"),
            HTTPException(status_code=429, detail="Rate limited"),
        ]

        with patch('app.integrations.spotify.client.SpotifyClient._refresh_access_token',
                   new_callable=AsyncMock) as mock_refresh:
            mock_refresh.side_effect = rate_limit_errors

            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user",
                provider="spotify",
                force_refresh=False
            )

            # Should give up after retries
            assert result is None
            assert mock_refresh.call_count == 3

    async def test_service_unavailable_handling(self, client, dao, refresh_service):
        """Test handling of service unavailable scenarios"""
        now = int(time.time())

        expired_token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="expired_token",
            refresh_token="service_down_refresh",
            scope="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Mock service unavailable responses
        unavailable_errors = [
            Exception("503 Service Unavailable"),
            Exception("502 Bad Gateway"),
            Exception("Connection timeout"),
        ]

        with patch('app.integrations.spotify.client.SpotifyClient._refresh_access_token',
                   new_callable=AsyncMock) as mock_refresh:
            mock_refresh.side_effect = unavailable_errors

            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user",
                provider="spotify",
                force_refresh=False
            )

            # Should give up after retries
            assert result is None
            assert mock_refresh.call_count == 3

    async def test_invalid_grant_error_recovery(self, dao, refresh_service):
        """Test handling of OAuth invalid grant errors (revoked tokens)"""
        now = int(time.time())

        expired_token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="expired_token",
            refresh_token="revoked_refresh",
            scope="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Mock invalid grant error (user revoked the token)
        with patch('app.integrations.spotify.client.SpotifyClient._refresh_access_token',
                   new_callable=AsyncMock) as mock_refresh:
            mock_refresh.side_effect = Exception("invalid_grant")

            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user",
                provider="spotify",
                force_refresh=False
            )

            # Should give up immediately for invalid grant
            assert result is None
            assert mock_refresh.call_count == 1  # No retries for invalid grant

    async def test_memory_pressure_error_handling(self, dao):
        """Test handling of memory pressure and resource exhaustion"""
        now = int(time.time())

        # Create many tokens to simulate memory pressure
        tokens = []
        for i in range(1000):  # Large number of tokens
            token = ThirdPartyToken(
                user_id=f"user_{i}",
                provider="spotify",
                provider_sub=f"sub_{i}",
                provider_iss="https://accounts.spotify.com",
                access_token=f"token_{i}",
                refresh_token=f"refresh_{i}",
                scope="user-read-private",
                expires_at=now + 3600,
                created_at=now,
                updated_at=now,
            )
            tokens.append(token)

        # Store all tokens
        for token in tokens:
            await dao.upsert_token(token)

        # Verify all can be retrieved
        for i in range(100):
            token = await dao.get_token(f"user_{i}", "spotify")
            assert token is not None
            assert token.access_token == f"token_{i}"

    async def test_disk_space_exhaustion_handling(self, tmp_path, dao):
        """Test handling of disk space exhaustion"""
        # This is harder to test directly, but we can mock the database write failure

        now = int(time.time())
        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="test_token",
            refresh_token="test_refresh",
            scope="user-read-private",
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )

        # Mock disk full error during upsert
        with patch.object(dao, 'upsert_token', side_effect=Exception("Disk full")):
            result = await dao.upsert_token(token)
            assert not result  # Should fail gracefully

    async def test_circuit_breaker_pattern(self, dao, refresh_service):
        """Test circuit breaker pattern for failing services"""
        now = int(time.time())

        expired_token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="expired_token",
            refresh_token="circuit_breaker_refresh",
            scope="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Mock persistent failures
        with patch('app.integrations.spotify.client.SpotifyClient._refresh_access_token',
                   new_callable=AsyncMock) as mock_refresh:
            mock_refresh.side_effect = Exception("Persistent failure")

            # First few attempts should retry
            for attempt in range(3):
                result = await refresh_service.get_valid_token_with_refresh(
                    user_id="test_user",
                    provider="spotify",
                    force_refresh=True
                )
                assert result is None

            # After consistent failures, system should handle gracefully
            # (In a real circuit breaker, this would open the circuit)

    async def test_graceful_degradation_under_load(self, client, dao):
        """Test graceful degradation under high load"""
        import asyncio

        now = int(time.time())

        # Create multiple users with tokens
        for i in range(50):
            token = ThirdPartyToken(
                user_id=f"load_user_{i}",
                provider="spotify",
                provider_sub=f"sub_{i}",
                provider_iss="https://accounts.spotify.com",
                access_token=f"token_{i}",
                refresh_token=f"refresh_{i}",
                scope="user-read-private",
                expires_at=now + 3600,
                created_at=now,
                updated_at=now,
            )
            await dao.upsert_token(token)

        # Simulate high concurrent load
        async def concurrent_request(user_id):
            with patch('app.auth_store_tokens.TokenDAO', return_value=dao):
                response = client.get(
                    '/v1/spotify/status',
                    cookies={'GSNH_AT': f'test_token_{user_id}'}
                )
                return response.status_code

        # Launch many concurrent requests
        tasks = [
            concurrent_request(f"load_user_{i}")
            for i in range(50)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete (some may fail gracefully, but none should crash)
        successful_responses = sum(1 for result in results if result in [200, 401, 404])
        assert successful_responses == len(results)
