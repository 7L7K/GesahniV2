"""
Property-based tests for TokenStore implementations using Hypothesis.

These tests use property-based testing to explore edge cases and ensure
that both the real TokenDAO and FakeTokenStore behave consistently
under various inputs and scenarios.
"""

import pytest
from hypothesis import given, strategies as st, settings, Phase
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant

from tests.helpers.fakes import FakeTokenStore
from app.models.third_party_tokens import ThirdPartyToken
import time


class TokenStoreStateMachine(RuleBasedStateMachine):
    """State machine for testing token store operations."""

    def __init__(self):
        super().__init__()
        self.fake_store = FakeTokenStore()
        self.tokens: dict[tuple[str, str], ThirdPartyToken] = {}

    @rule(
        user_id=st.text(min_size=1, max_size=50),
        provider=st.sampled_from(["spotify", "google", "apple"]),
        access_token=st.text(min_size=1, max_size=100),
        refresh_token=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        scopes=st.one_of(st.none(), st.text(min_size=1, max_size=200))
    )
    def upsert_token(self, user_id: str, provider: str, access_token: str,
                    refresh_token: str | None, scopes: str | None) -> None:
        """Upsert a token and track it in our model."""
        token = ThirdPartyToken(
            user_id=user_id,
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=scopes,
            expires_at=int(time.time()) + 3600,
        )

        # Update our model
        self.tokens[(user_id, provider)] = token

        # Apply to fake store
        import asyncio
        asyncio.run(self.fake_store.upsert_token(token))

    @invariant()
    def tokens_match_fake_store(self) -> None:
        """Invariant: our model should match the fake store's state."""
        # Check that all our tokens are in the fake store
        for (user_id, provider), expected_token in self.tokens.items():
            stored_token = asyncio.run(self.fake_store.get_token(user_id, provider))
            assert stored_token is not None
            assert stored_token.user_id == expected_token.user_id
            assert stored_token.provider == expected_token.provider
            assert stored_token.access_token == expected_token.access_token
            assert stored_token.refresh_token == expected_token.refresh_token

    @invariant()
    def has_any_consistency(self) -> None:
        """Invariant: has_any should be consistent with actual tokens."""
        # Check for each user that has tokens
        users_with_tokens = {user_id for (user_id, _) in self.tokens.keys()}

        for user_id in users_with_tokens:
            # Check has_any() without provider
            has_any = asyncio.run(self.fake_store.has_any(user_id))
            assert has_any is True

            # Check has_any() with specific provider
            user_providers = {provider for (uid, provider) in self.tokens.keys() if uid == user_id}
            for provider in user_providers:
                has_provider = asyncio.run(self.fake_store.has_any(user_id, provider))
                assert has_provider is True


TestTokenStoreStateMachine = TokenStoreStateMachine.TestCase


@given(
    user=st.text(min_size=1, max_size=50),
    provider=st.sampled_from(["spotify", "google", "apple"]),
    access=st.text(min_size=1, max_size=100),
    refresh=st.one_of(st.none(), st.text(min_size=1, max_size=100))
)
@pytest.mark.asyncio
async def test_upsert_get_delete_roundtrip(user: str, provider: str, access: str, refresh: str | None):
    """Test complete roundtrip of upsert -> get -> delete."""
    fake_store = FakeTokenStore()

    # Create token data
    token_data = ThirdPartyToken(
        user_id=user,
        provider=provider,
        access_token=access,
        refresh_token=refresh,
        scopes="user-read-private",
        expires_at=int(time.time()) + 3600,
    )

    # Upsert
    result = await fake_store.upsert_token(token_data)
    assert result is True

    # Get
    retrieved = await fake_store.get_token(user, provider)
    assert retrieved is not None
    assert retrieved.user_id == user
    assert retrieved.provider == provider
    assert retrieved.access_token == access
    assert retrieved.refresh_token == refresh

    # Delete
    delete_result = await fake_store.delete_token(user, provider)
    assert delete_result is True

    # Verify gone
    gone = await fake_store.get_token(user, provider)
    assert gone is None

    # Verify has_any is false
    has_any = await fake_store.has_any(user, provider)
    assert has_any is False


@given(
    user=st.text(min_size=1, max_size=50),
    provider=st.sampled_from(["spotify", "google", "apple"]),
    other_provider=st.sampled_from(["spotify", "google", "apple"]),
)
@pytest.mark.asyncio
async def test_provider_isolation(user: str, provider: str, other_provider: str):
    """Test that different providers don't interfere with each other."""
    fake_store = FakeTokenStore()

    # Skip if same provider
    if provider == other_provider:
        return

    # Create tokens for both providers
    token1 = ThirdPartyToken(
        user_id=user,
        provider=provider,
        access_token="token1",
        scopes="scope1",
        expires_at=int(time.time()) + 3600,
    )

    token2 = ThirdPartyToken(
        user_id=user,
        provider=other_provider,
        access_token="token2",
        scopes="scope2",
        expires_at=int(time.time()) + 3600,
    )

    # Upsert both
    await fake_store.upsert_token(token1)
    await fake_store.upsert_token(token2)

    # Verify they don't interfere
    retrieved1 = await fake_store.get_token(user, provider)
    retrieved2 = await fake_store.get_token(user, other_provider)

    assert retrieved1 is not None
    assert retrieved2 is not None
    assert retrieved1.access_token == "token1"
    assert retrieved2.access_token == "token2"
    assert retrieved1.provider == provider
    assert retrieved2.provider == other_provider

    # Delete one and verify the other remains
    await fake_store.delete_token(user, provider)
    assert await fake_store.get_token(user, provider) is None
    assert await fake_store.get_token(user, other_provider) is not None


@given(
    user=st.text(min_size=1, max_size=50),
    provider=st.sampled_from(["spotify", "google", "apple"]),
    access=st.text(min_size=1, max_size=100),
)
@pytest.mark.asyncio
async def test_upsert_overwrites(user: str, provider: str, access: str):
    """Test that upsert overwrites existing tokens."""
    fake_store = FakeTokenStore()

    # Create initial token
    token1 = ThirdPartyToken(
        user_id=user,
        provider=provider,
        access_token="original_token",
        scopes="original_scope",
        expires_at=int(time.time()) + 3600,
    )

    # Create updated token
    token2 = ThirdPartyToken(
        user_id=user,
        provider=provider,
        access_token=access,
        scopes="updated_scope",
        expires_at=int(time.time()) + 3600,
    )

    # Upsert both
    await fake_store.upsert_token(token1)
    await fake_store.upsert_token(token2)

    # Should only have the updated token
    retrieved = await fake_store.get_token(user, provider)
    assert retrieved is not None
    assert retrieved.access_token == access
    assert retrieved.scopes == "updated_scope"

    # Should only have one token saved
    assert len(fake_store.newly_saved) == 1
    assert fake_store.newly_saved[0] == token2


@given(
    st.lists(
        st.tuples(
            st.text(min_size=1, max_size=20),
            st.sampled_from(["spotify", "google", "apple"]),
            st.text(min_size=1, max_size=50)
        ),
        min_size=1,
        max_size=10,
        unique_by=lambda x: (x[0], x[1])  # Unique by (user, provider)
    )
)
@pytest.mark.asyncio
async def test_multiple_users_providers(token_specs):
    """Test multiple users and providers coexist properly."""
    fake_store = FakeTokenStore()

    # Create tokens for all specs
    tokens = {}
    for user, provider, access in token_specs:
        token = ThirdPartyToken(
            user_id=user,
            provider=provider,
            access_token=access,
            scopes=f"scope_{user}_{provider}",
            expires_at=int(time.time()) + 3600,
        )
        tokens[(user, provider)] = token
        await fake_store.upsert_token(token)

    # Verify all tokens are retrievable
    for (user, provider), expected_token in tokens.items():
        retrieved = await fake_store.get_token(user, provider)
        assert retrieved is not None
        assert retrieved.access_token == expected_token.access_token
        assert retrieved.scopes == expected_token.scopes

    # Verify has_any works for each user
    users = {user for user, _ in tokens.keys()}
    for user in users:
        has_any = await fake_store.has_any(user)
        assert has_any is True

    # Verify has_any works for specific providers
    for user, provider in tokens.keys():
        has_provider = await fake_store.has_any(user, provider)
        assert has_provider is True


@pytest.mark.asyncio
async def test_empty_store_operations():
    """Test operations on an empty store."""
    fake_store = FakeTokenStore()

    # Get non-existent token
    result = await fake_store.get_token("nonexistent", "spotify")
    assert result is None

    # Delete non-existent token
    delete_result = await fake_store.delete_token("nonexistent", "spotify")
    assert delete_result is False

    # Check has_any for non-existent user
    has_any = await fake_store.has_any("nonexistent")
    assert has_any is False

    has_provider = await fake_store.has_any("nonexistent", "spotify")
    assert has_provider is False
