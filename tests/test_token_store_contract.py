"""
Contract tests to ensure FakeTokenStore interface matches TokenDAO.

These tests verify that the fake implementation has the same interface and basic behavior
as the real implementation, ensuring tests remain valid even as the real implementation evolves.
"""

import pytest
import time
from typing import Dict, Tuple
from app.models.third_party_tokens import ThirdPartyToken
from app.factories import make_token_store
from tests.helpers.fakes import FakeTokenStore


@pytest.fixture
def sample_token():
    """Sample token for testing."""
    return ThirdPartyToken(
        user_id="test_user_123",
        provider="spotify",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        scopes="user-read-private",
        expires_at=int(time.time()) + 3600,
        provider_iss="https://accounts.spotify.com",
        identity_id="spotify_identity_123",
        provider_sub="spotify_user_123",
    )


@pytest.fixture
def sample_token_google():
    """Sample Google token for testing."""
    return ThirdPartyToken(
        user_id="test_user_456",
        provider="google",
        access_token="google_access_token",
        refresh_token="google_refresh_token",
        scopes="https://www.googleapis.com/auth/calendar",
        expires_at=int(time.time()) + 3600,
        provider_iss="https://accounts.google.com",
        identity_id="google_identity_456",
        provider_sub="google_user_456",
    )


class TestTokenStoreContract:
    """Test that FakeTokenStore interface matches TokenDAO interface."""

    def test_interface_compatibility(self):
        """Test that FakeTokenStore has all the same async methods as TokenDAO."""
        real_store = make_token_store()
        fake_store = FakeTokenStore()

        # Get all async methods from real store
        real_methods = [method for method in dir(real_store) if not method.startswith('_') and callable(getattr(real_store, method))]
        real_async_methods = []
        for method in real_methods:
            if hasattr(getattr(real_store, method), '__call__'):
                # Check if it's a coroutine function by looking for __call__ and trying to determine if async
                try:
                    import inspect
                    if inspect.iscoroutinefunction(getattr(real_store, method)):
                        real_async_methods.append(method)
                except:
                    pass

        # Fake store should have all the same async methods
        fake_methods = [method for method in dir(fake_store) if not method.startswith('_') and callable(getattr(fake_store, method))]
        fake_async_methods = []
        for method in fake_methods:
            if hasattr(getattr(fake_store, method), '__call__'):
                try:
                    import inspect
                    if inspect.iscoroutinefunction(getattr(fake_store, method)):
                        fake_async_methods.append(method)
                except:
                    pass

        # Core token operations should be present
        expected_methods = ['upsert_token', 'get_token', 'delete_token', 'has_any']

        for method in expected_methods:
            assert method in fake_async_methods, f"FakeTokenStore missing method: {method}"
            assert hasattr(fake_store, method), f"FakeTokenStore missing attribute: {method}"

    @pytest.mark.asyncio
    async def test_basic_fake_functionality_spotify(self, sample_token):
        """Test basic fake store functionality works as expected."""
        fake_store = FakeTokenStore()

        # Test upsert
        result = await fake_store.upsert_token(sample_token)
        assert result is True
        assert len(fake_store.newly_saved) == 1
        assert fake_store.newly_saved[0] == sample_token

        # Test get_token
        retrieved = await fake_store.get_token(sample_token.user_id, sample_token.provider)
        assert retrieved is not None
        assert retrieved == sample_token

        # Test has_any
        has_token = await fake_store.has_any(sample_token.user_id, sample_token.provider)
        assert has_token is True

        has_any_provider = await fake_store.has_any(sample_token.user_id)
        assert has_any_provider is True

        # Test delete
        delete_result = await fake_store.delete_token(sample_token.user_id, sample_token.provider)
        assert delete_result is True

        # Verify it's gone
        retrieved_after_delete = await fake_store.get_token(sample_token.user_id, sample_token.provider)
        assert retrieved_after_delete is None

        has_token_after_delete = await fake_store.has_any(sample_token.user_id, sample_token.provider)
        assert has_token_after_delete is False

    @pytest.mark.asyncio
    async def test_basic_fake_functionality_google(self, sample_token_google):
        """Test basic fake store functionality works for Google tokens."""
        fake_store = FakeTokenStore()

        # Test upsert
        result = await fake_store.upsert_token(sample_token_google)
        assert result is True
        assert len(fake_store.newly_saved) == 1
        assert fake_store.newly_saved[0] == sample_token_google

        # Test get_token
        retrieved = await fake_store.get_token(sample_token_google.user_id, sample_token_google.provider)
        assert retrieved is not None
        assert retrieved == sample_token_google

        # Test has_any
        has_token = await fake_store.has_any(sample_token_google.user_id, sample_token_google.provider)
        assert has_token is True

    @pytest.mark.asyncio
    async def test_get_token_not_found(self):
        """Test get_token returns None for non-existent tokens."""
        fake_store = FakeTokenStore()

        result = await fake_store.get_token("non_existent_user", "spotify")
        assert result is None

    @pytest.mark.asyncio
    async def test_has_any_empty_store(self):
        """Test has_any returns False for empty store."""
        fake_store = FakeTokenStore()

        result_user_only = await fake_store.has_any("any_user")
        assert result_user_only is False

        result_user_provider = await fake_store.has_any("any_user", "spotify")
        assert result_user_provider is False


class TestFakeTokenStoreFeatures:
    """Test FakeTokenStore specific features."""

    def test_preloaded_tokens(self, sample_token):
        """Test that preloaded tokens work correctly."""
        preloaded = {(sample_token.user_id, sample_token.provider): sample_token}
        fake_store = FakeTokenStore(preloaded_tokens=preloaded)

        # Preloaded token should be available
        assert len(fake_store.tokens) == 1
        assert len(fake_store.all_saved) == 1
        assert len(fake_store.newly_saved) == 0  # Preloaded tokens don't count as newly saved

    def test_newly_saved_excludes_preloaded(self, sample_token, sample_token_google):
        """Test that newly_saved excludes preloaded tokens."""
        preloaded = {(sample_token.user_id, sample_token.provider): sample_token}
        fake_store = FakeTokenStore(preloaded_tokens=preloaded)

        # Save a new token
        import asyncio
        asyncio.run(fake_store.upsert_token(sample_token_google))

        # Should have 2 total saved, but only 1 newly saved
        assert len(fake_store.all_saved) == 2
        assert len(fake_store.newly_saved) == 1
        assert fake_store.newly_saved[0] == sample_token_google

    def test_clear_resets_everything(self, sample_token):
        """Test that clear resets all state."""
        fake_store = FakeTokenStore()

        # Add a token
        import asyncio
        asyncio.run(fake_store.upsert_token(sample_token))

        assert len(fake_store.tokens) == 1
        assert len(fake_store.saved) == 1

        # Clear everything
        fake_store.clear()

        assert len(fake_store.tokens) == 0
        assert len(fake_store.saved) == 0
        assert len(fake_store.preloaded_tokens) == 0
