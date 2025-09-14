"""
Tests for the TokenRefreshService - automatic token refresh functionality
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.auth_store_tokens import TokenDAO, TokenRefreshService
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
class TestTokenRefreshService:
    """Test the automatic token refresh service"""

    @pytest.fixture
    async def dao(self, tmp_path):
        """Create a fresh TokenDAO for each test"""
        db_path = str(tmp_path / "test_refresh.db")
        dao = TokenDAO(db_path)
        yield dao

    @pytest.fixture
    def refresh_service(self):
        """Create TokenRefreshService instance"""
        return TokenRefreshService()

    async def test_successful_token_refresh_spotify(self, tmp_path, refresh_service):
        """Test successful token refresh for Spotify"""
        db_path = str(tmp_path / "test_refresh.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Create expired token
        expired_token = ThirdPartyToken(
            identity_id="c3f59397-38d2-475d-a0ef-24d1ec86c908",
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now - 3600,  # Already expired
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        # Store the expired token
        await dao.upsert_token(expired_token)

        # Mock the Spotify refresh function
        new_access_token = "new_fresh_token_789"
        new_expires_at = now + 3600

        with patch(
            "app.integrations.spotify.client.SpotifyClient._refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            mock_refresh.return_value = {
                "access_token": new_access_token,
                "expires_at": new_expires_at,
            }

            # Try to get valid token (should trigger refresh)
            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user", provider="spotify", force_refresh=False
            )

            # Should have gotten the refreshed token
            assert result is not None
            assert result.access_token == new_access_token
            assert result.expires_at == new_expires_at

            # Verify refresh was called
            mock_refresh.assert_called_once()

    async def test_refresh_retry_on_failure(self, dao, refresh_service):
        """Test retry logic when refresh fails"""
        now = int(time.time())

        # Create expired token
        expired_token = ThirdPartyToken(
            identity_id="f36694db-e45f-4dbc-ba67-7de5b0896750",
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Mock refresh to fail twice then succeed
        with patch(
            "app.integrations.spotify.client.SpotifyClient._refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            mock_refresh.side_effect = [
                Exception("Network error"),
                Exception("Server error"),
                {"access_token": "final_token_999", "expires_at": now + 3600},
            ]

            # Try to get valid token
            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user", provider="spotify", force_refresh=False
            )

            # Should eventually succeed
            assert result is not None
            assert result.access_token == "final_token_999"

            # Should have been called 3 times (initial + 2 retries)
            assert mock_refresh.call_count == 3

    async def test_refresh_exhaustion_gives_up(self, dao, refresh_service):
        """Test that refresh gives up after max retries"""
        now = int(time.time())

        # Create expired token
        expired_token = ThirdPartyToken(
            identity_id="ba9cfce6-2d9b-49a8-9541-45b37346bcc9",
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Mock refresh to always fail
        with patch(
            "app.integrations.spotify.client.SpotifyClient._refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            mock_refresh.side_effect = Exception("Persistent failure")

            # Try to get valid token
            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user", provider="spotify", force_refresh=False
            )

            # Should return None after exhausting retries
            assert result is None

            # Should have been called max_attempts times (default 3)
            assert mock_refresh.call_count == 3

    async def test_concurrent_refresh_protection(self, dao, refresh_service):
        """Test that concurrent refresh attempts are protected"""
        now = int(time.time())

        # Create expired token
        expired_token = ThirdPartyToken(
            identity_id="5ce21d91-41a1-4c27-8517-eab108392ea0",
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_token)

        # Create slow refresh mock (takes time)
        refresh_called = 0

        async def slow_refresh(*args, **kwargs):
            nonlocal refresh_called
            refresh_called += 1
            await asyncio.sleep(0.1)  # Simulate network delay
            return {"access_token": f"token_{refresh_called}", "expires_at": now + 3600}

        with patch(
            "app.integrations.spotify.client.SpotifyClient._refresh_access_token",
            side_effect=slow_refresh,
        ):
            # Start multiple concurrent refresh attempts
            tasks = []
            for _i in range(5):
                task = refresh_service.get_valid_token_with_refresh(
                    user_id="test_user", provider="spotify", force_refresh=False
                )
                tasks.append(task)

            # Wait for all to complete
            results = await asyncio.gather(*tasks)

            # All should get the same result
            for result in results:
                assert result is not None
                assert (
                    result.access_token == "token_1"
                )  # Only first refresh should happen

            # Refresh should only be called once due to concurrency protection
            assert refresh_called == 1

    async def test_force_refresh_bypasses_cache(self, dao, refresh_service):
        """Test that force_refresh=True bypasses any caching"""
        now = int(time.time())

        # Create fresh token (not expired)
        fresh_token = ThirdPartyToken(
            identity_id="877720f0-4104-4913-ad4b-c259714a8404",
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now + 3600,  # Still fresh
            created_at=now,
            updated_at=now,
        )

        await dao.upsert_token(fresh_token)

        with patch(
            "app.integrations.spotify.client.SpotifyClient._refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            mock_refresh.return_value = {
                "access_token": "forced_refresh_token_789",
                "expires_at": now + 3600,
            }

            # Get token with force_refresh=False (should not refresh)
            result1 = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user", provider="spotify", force_refresh=False
            )

            # Should get original token
            assert result1.access_token == "original_token_123"
            assert not mock_refresh.called

            # Get token with force_refresh=True (should refresh anyway)
            result2 = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user", provider="spotify", force_refresh=True
            )

            # Should get refreshed token
            assert result2.access_token == "forced_refresh_token_789"
            assert mock_refresh.called

    async def test_google_token_refresh(self, dao, refresh_service):
        """Test refresh works for Google tokens too"""
        now = int(time.time())

        # Create expired Google token
        expired_google = ThirdPartyToken(
            identity_id="74c7ab61-d396-4ab3-8959-a5c9404bff89",
            user_id="test_user",
            provider="google",
            provider_sub="google_user_123",
            provider_iss="https://accounts.google.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="https://www.googleapis.com/auth/calendar.readonly",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(expired_google)

        # Mock Google refresh
        with patch(
            "app.integrations.google.client.GoogleClient._refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            mock_refresh.return_value = {
                "access_token": "new_google_token_999",
                "expires_at": now + 3600,
            }

            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user", provider="google", force_refresh=False
            )

            assert result is not None
            assert result.access_token == "new_google_token_999"
            assert mock_refresh.called

    async def test_no_token_found_handling(self, dao, refresh_service):
        """Test handling when no token exists for user/provider"""
        # Don't create any tokens

        result = await refresh_service.get_valid_token_with_refresh(
            user_id="nonexistent_user", provider="spotify", force_refresh=False
        )

        # Should return None gracefully
        assert result is None

    async def test_invalid_refresh_token_handling(self, dao, refresh_service):
        """Test handling of invalid/broken refresh tokens"""
        now = int(time.time())

        # Create token with invalid refresh token
        broken_token = ThirdPartyToken(
            identity_id="07afcfef-537a-4ca6-8a3d-f25566ad3e7e",
            user_id="test_user",
            provider="spotify",
            provider_sub="spotify_user_123",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="user-read-private",
            expires_at=now - 3600,
            created_at=now - 7200,
            updated_at=now - 7200,
        )

        await dao.upsert_token(broken_token)

        # Mock refresh to fail with invalid token error
        with patch(
            "app.integrations.spotify.client.SpotifyClient._refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh:
            mock_refresh.side_effect = Exception("Invalid refresh token")

            result = await refresh_service.get_valid_token_with_refresh(
                user_id="test_user", provider="spotify", force_refresh=False
            )

            # Should return None after all retries
            assert result is None
            assert mock_refresh.call_count == 3  # All retries exhausted
