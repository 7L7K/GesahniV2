"""Test the persistence contract - DAOs that can be relied on."""

import tempfile
from pathlib import Path

import pytest

from app.auth_store_tokens import TokenDAO
from app.db.migrate import run_all_migrations
from app.models.third_party_tokens import ThirdPartyToken
from app.models.user_stats import UserStats
from app.user_store import UserDAO


class TestPersistenceContract:
    """Test that persistence contract is fulfilled."""

    @pytest.fixture
    def temp_db_dir(self):
        """Create a temporary directory for test databases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_token_dao_interface_contract(self, temp_db_dir):
        """Test TokenDAO fulfills the required interface contract."""
        # Create DAO with temp path
        dao = TokenDAO(str(temp_db_dir / "tokens.db"))

        # Test ensure_schema_migrated
        import asyncio
        asyncio.run(dao.ensure_schema_migrated())

        # Test persist (via upsert_token) - mock the validation for this test
        import time
        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            access_token="test_access_token_that_is_long_enough_for_validation",
            provider_sub="test_sub",
            provider_iss="https://accounts.spotify.com",
            identity_id="test_identity_123",
            scopes="playlist-read-private",
            expires_at=int(time.time()) + 3600,  # Valid future timestamp (1 hour from now)
            is_valid=True
        )

        # Mock the validation methods to return True for this test
        from unittest.mock import patch
        with patch.object(dao, '_validate_spotify_token_contract', return_value=True), \
             patch.object(dao, '_validate_token_for_storage', return_value=True):
            result = asyncio.run(dao.persist(token))
            assert result is True

            # Test get_by_id
            retrieved = asyncio.run(dao.get_by_id(token.id))
            assert retrieved is not None
            assert retrieved.id == token.id
            assert retrieved.user_id == token.user_id
            assert retrieved.provider == token.provider

            # Test revoke_family
            revoke_result = asyncio.run(dao.revoke_family(token.user_id, token.provider))
            assert revoke_result is True

    def test_user_dao_interface_contract(self, temp_db_dir):
        """Test UserDAO fulfills the required interface contract."""
        # Create DAO with temp path
        dao = UserDAO(temp_db_dir / "users.db")

        # Test ensure_schema_migrated
        import asyncio
        asyncio.run(dao.ensure_schema_migrated())

        # Test persist
        stats = UserStats(
            user_id="test_user",
            login_count=5,
            request_count=10
        )

        result = asyncio.run(dao.persist(stats))
        assert result is True

        # Test get_by_id
        retrieved = asyncio.run(dao.get_by_id(stats.user_id))
        assert retrieved is not None
        assert retrieved.user_id == stats.user_id
        assert retrieved.login_count == stats.login_count
        assert retrieved.request_count == stats.request_count

        # Test revoke_family (should return True for user stats)
        revoke_result = asyncio.run(dao.revoke_family(stats.user_id))
        assert revoke_result is True

    def test_migration_system_works(self, temp_db_dir):
        """Test that the migration system can run on a fresh database directory."""
        # This should work without any manual DB setup
        import asyncio
        asyncio.run(run_all_migrations(temp_db_dir))

        # Verify databases were created
        assert (temp_db_dir / "third_party_tokens.db").exists()
        assert (temp_db_dir / "users.db").exists()

    def test_daos_return_typed_models_not_dicts(self, temp_db_dir):
        """Test that DAOs return Pydantic models, not raw dicts."""
        # TokenDAO
        token_dao = TokenDAO(str(temp_db_dir / "tokens.db"))
        import asyncio
        asyncio.run(token_dao.ensure_schema_migrated())

        import time
        token = ThirdPartyToken(
            user_id="test_user",
            provider="spotify",
            access_token="test_access_token_that_is_long_enough_for_validation",
            provider_iss="https://accounts.spotify.com",
            identity_id="test_identity_123",
            scopes="playlist-read-private",
            expires_at=int(time.time()) + 3600,  # Valid future timestamp (1 hour from now)
            is_valid=True
        )

        # Mock the validation methods to return True for this test
        from unittest.mock import patch
        with patch.object(token_dao, '_validate_spotify_token_contract', return_value=True), \
             patch.object(token_dao, '_validate_token_for_storage', return_value=True):
            asyncio.run(token_dao.persist(token))
            retrieved = asyncio.run(token_dao.get_by_id(token.id))

            assert retrieved is not None
        assert isinstance(retrieved, ThirdPartyToken)
        assert hasattr(retrieved, 'user_id')  # Pydantic model attribute
        assert not isinstance(retrieved, dict)  # Not a raw dict

        # UserDAO
        user_dao = UserDAO(temp_db_dir / "users.db")
        asyncio.run(user_dao.ensure_schema_migrated())

        stats = UserStats(user_id="test_user", login_count=1)
        asyncio.run(user_dao.persist(stats))
        retrieved_stats = asyncio.run(user_dao.get_by_id(stats.user_id))

        assert retrieved_stats is not None
        assert isinstance(retrieved_stats, UserStats)
        assert hasattr(retrieved_stats, 'login_count')  # Pydantic model attribute
        assert not isinstance(retrieved_stats, dict)  # Not a raw dict
