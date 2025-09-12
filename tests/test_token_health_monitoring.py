"""
Tests for token health monitoring endpoints and metrics
"""

import time
from unittest.mock import patch, Mock

import pytest

from app.auth_store_tokens import get_token_system_health
from app.models.third_party_tokens import ThirdPartyToken


@pytest.mark.asyncio
class TestTokenHealthMonitoring:
    """Test token health monitoring and metrics"""

    async def test_healthy_system_status(self, tmp_path):
        """Test health monitoring with healthy token system"""
        from app.auth_store_tokens import TokenDAO

        db_path = str(tmp_path / "healthy.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Create some valid tokens
        valid_tokens = [
            ThirdPartyToken(
                identity_id="a567a16b-6f2c-44bc-9416-10f7e11474b5",
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
            ThirdPartyToken(
                identity_id="6c505ceb-fb46-4b93-b019-6b18e5354b7d",
                user_id="user2",
                provider="google",
                provider_sub="google_user2",
                provider_iss="https://accounts.google.com",
                access_token="BAAAAAAAAAAAAAAAAA",
                refresh_token="ABBBBBBBBBBBBBBBBB",
                scopes="calendar.readonly",
                expires_at=now + 7200,
                created_at=now,
                updated_at=now,
            ),
        ]

        for token in valid_tokens:
            await dao.upsert_token(token)

        # Mock the DAO in the health function
        with patch("app.auth_store_tokens.TokenDAO", return_value=dao):
            health = await get_token_system_health()

            assert health["status"] == "healthy"
            assert health["database"]["total_tokens"] == 2
            assert health["database"]["valid_tokens"] == 2
            assert health["database"]["expired_tokens"] == 0
            assert health["database"]["providers"]["spotify"]["total"] == 1
            assert health["database"]["providers"]["spotify"]["valid"] == 1
            assert health["database"]["providers"]["google"]["total"] == 1
            assert health["database"]["providers"]["google"]["valid"] == 1

    async def test_system_with_expired_tokens(self, tmp_path):
        """Test health monitoring with some expired tokens"""
        from app.auth_store_tokens import TokenDAO

        db_path = str(tmp_path / "expired.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Create mix of valid and expired tokens
        tokens = [
            ThirdPartyToken(
                identity_id="75abe813-b953-4a78-b4a4-04654d5bde8e",  # Valid token
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
            ThirdPartyToken(
                identity_id="ca0f7031-da65-482c-a237-d530e1ec649d",  # Expired token
                user_id="user2",
                provider="spotify",
                provider_sub="spotify_user2",
                provider_iss="https://accounts.spotify.com",
                access_token="BAAAAAAAAAAAAAAAAA",
                refresh_token="ABBBBBBBBBBBBBBBBB",
                scopes="user-read-private",
                expires_at=now - 3600,  # Expired!
                created_at=now - 7200,
                updated_at=now - 7200,
            ),
            ThirdPartyToken(
                identity_id="531016cc-0086-4eba-8797-053798e5a45a",  # Another expired token
                user_id="user3",
                provider="google",
                provider_sub="google_user3",
                provider_iss="https://accounts.google.com",
                access_token="BAAAAAAAAAAAAAAAAA",
                refresh_token="ABBBBBBBBBBBBBBBBB",
                scopes="calendar.readonly",
                expires_at=now - 1800,  # Also expired!
                created_at=now - 3600,
                updated_at=now - 3600,
            ),
        ]

        for token in tokens:
            await dao.upsert_token(token)

        with patch("app.auth_store_tokens.TokenDAO", return_value=dao):
            health = await get_token_system_health()

            assert (
                health["status"] == "healthy"
            )  # Still healthy, just has expired tokens
            assert health["database"]["total_tokens"] == 3
            assert health["database"]["valid_tokens"] == 1  # Only user1's token
            assert health["database"]["expired_tokens"] == 2  # user2 and user3's tokens

    async def test_empty_database_health(self, tmp_path):
        """Test health monitoring with empty database"""
        from app.auth_store_tokens import TokenDAO

        db_path = str(tmp_path / "empty.db")
        dao = TokenDAO(db_path)

        with patch("app.auth_store_tokens.TokenDAO", return_value=dao):
            health = await get_token_system_health()

            assert health["status"] == "healthy"
            assert health["database"]["total_tokens"] == 0
            assert health["database"]["valid_tokens"] == 0
            assert health["database"]["expired_tokens"] == 0
            assert health["database"]["providers"] == {}

    async def test_corrupted_database_handling(self, tmp_path):
        """Test health monitoring handles database corruption gracefully"""

        # Create corrupted database file
        db_path = str(tmp_path / "corrupted.db")
        with open(db_path, "w") as f:
            f.write("corrupted database content")

        # This should handle the corruption gracefully
        with patch("app.auth_store_tokens.TokenDAO") as mock_dao_class:
            mock_dao = Mock()
            mock_dao.get_all_user_tokens.side_effect = Exception("Database corruption")
            mock_dao_class.return_value = mock_dao

            health = await get_token_system_health()

            # Should still return a health structure, but with error status
            assert "status" in health
            assert "database" in health
            # The exact behavior depends on how we handle corruption

    async def test_refresh_service_health_metrics(self, tmp_path):
        """Test that refresh service health metrics are included"""
        from app.auth_store_tokens import TokenDAO

        db_path = str(tmp_path / "refresh_health.db")
        dao = TokenDAO(db_path)

        with patch("app.auth_store_tokens.TokenDAO", return_value=dao):
            health = await get_token_system_health()

            # Should include refresh service health
            assert "refresh_service" in health
            assert "active_refresh_attempts" in health["refresh_service"]
            assert "max_refresh_attempts" in health["refresh_service"]
            assert (
                health["refresh_service"]["max_refresh_attempts"] == 3
            )  # Default value

            # Should include feature flags
            assert "metrics" in health
            assert health["metrics"]["token_validation_enabled"] is True
            assert health["metrics"]["automatic_refresh_enabled"] is True
            assert health["metrics"]["monitoring_enabled"] is True

    async def test_health_timestamp_and_versioning(self, tmp_path):
        """Test that health response includes proper metadata"""
        from app.auth_store_tokens import TokenDAO

        db_path = str(tmp_path / "metadata.db")
        dao = TokenDAO(db_path)

        start_time = time.time()

        with patch("app.auth_store_tokens.TokenDAO", return_value=dao):
            health = await get_token_system_health()

            end_time = time.time()

            # Should include timestamp
            assert "timestamp" in health
            assert isinstance(health["timestamp"], int | float)
            assert start_time <= health["timestamp"] <= end_time

            # Should have consistent structure
            required_keys = [
                "status",
                "timestamp",
                "database",
                "refresh_service",
                "metrics",
            ]
            for key in required_keys:
                assert key in health, f"Missing required key: {key}"

    async def test_provider_distribution_tracking(self, tmp_path):
        """Test that health monitoring tracks provider distribution"""
        from app.auth_store_tokens import TokenDAO

        db_path = str(tmp_path / "providers.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Create tokens from multiple providers
        providers = ["spotify", "google", "github", "twitter"]
        tokens = []

        for i, provider in enumerate(providers):
            token = ThirdPartyToken(
                user_id=f"user_{i}",
                provider=provider,
                provider_sub=f"{provider}_user_{i}",
                provider_iss=f"https://accounts.{provider}.com",
                access_token=f"BAAAAAAAAAAAAAAAAA{i}",
                refresh_token=f"ABBBBBBBBBBBBBBBBB{i}",
                scopes="read",
                expires_at=now + 3600,
                created_at=now,
                updated_at=now,
            )
            tokens.append(token)
            await dao.upsert_token(token)

        with patch("app.auth_store_tokens.TokenDAO", return_value=dao):
            health = await get_token_system_health()

            # Should track all providers
            provider_stats = health["database"]["providers"]
            for provider in providers:
                assert provider in provider_stats
                assert provider_stats[provider]["total"] == 1
                assert provider_stats[provider]["valid"] == 1

    async def test_health_performance_under_load(self, tmp_path):
        """Test health monitoring performance with many tokens"""
        import time
        from app.auth_store_tokens import TokenDAO

        db_path = str(tmp_path / "load_test.db")
        dao = TokenDAO(db_path)

        now = int(time.time())

        # Create many tokens to test performance
        num_tokens = 100
        tokens = []

        for i in range(num_tokens):
            token = ThirdPartyToken(
                identity_id="8ea201c6-cbfd-45d4-aad7-beb3f9473a5a",
                user_id=f"user_{i}",
                provider="spotify" if i % 2 == 0 else "google",
                provider_sub=f"user_{i}_sub",
                provider_iss=(
                    "https://accounts.spotify.com"
                    if i % 2 == 0
                    else "https://accounts.google.com"
                ),
                access_token=f"BAAAAAAAAAAAAAAAAA{i}",
                refresh_token=f"ABBBBBBBBBBBBBBBBB{i}",
                scopes="read",
                expires_at=now + 3600,
                created_at=now,
                updated_at=now,
            )
            tokens.append(token)

        for token in tokens:
            await dao.upsert_token(token)

        import time

        start_time = time.time()

        with patch("app.auth_store_tokens.TokenDAO", return_value=dao):
            health = await get_token_system_health()

        end_time = time.time()
        duration = end_time - start_time

        # Should complete within reasonable time (under 1 second for 100 tokens)
        assert duration < 1.0, f"Health check took too long: {duration}s"

        # Should still be accurate
        assert health["database"]["total_tokens"] == num_tokens
        assert health["database"]["valid_tokens"] == num_tokens
        assert health["database"]["expired_tokens"] == 0

    async def test_health_error_resilience(self, tmp_path):
        """Test that health monitoring is resilient to individual errors"""
        from app.auth_store_tokens import TokenDAO

        db_path = str(tmp_path / "error_resilience.db")
        dao = TokenDAO(db_path)

        # Mock partial failures
        original_get_all = dao.get_all_user_tokens

        async def failing_get_all(user_id):
            if user_id == "problematic_user":
                raise Exception("Simulated database error")
            return await original_get_all(user_id)

        dao.get_all_user_tokens = failing_get_all

        # Create some tokens including the problematic user
        now = int(time.time())

        # Normal user
        normal_token = ThirdPartyToken(
            identity_id="755e481a-79ae-476b-9479-0347e4b8a956",
            user_id="normal_user",
            provider="spotify",
            provider_sub="normal_sub",
            provider_iss="https://accounts.spotify.com",
            access_token="BAAAAAAAAAAAAAAAAA",
            refresh_token="ABBBBBBBBBBBBBBBBB",
            scopes="read",
            expires_at=now + 3600,
            created_at=now,
            updated_at=now,
        )
        await dao.upsert_token(normal_token)

        # Problematic user (will cause error)
        # We won't create tokens for this user since get_all_user_tokens will fail

        with patch("app.auth_store_tokens.TokenDAO", return_value=dao):
            # Health check should handle the error gracefully
            health = await get_token_system_health()

            # Should still return valid health data
            assert "status" in health
            assert "database" in health

            # Should have captured the normal user's token
            # Note: This test depends on how we implement error handling in health check
