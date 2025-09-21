"""
Protocol for token store implementations.

This Protocol ensures that both the real TokenDAO and FakeTokenStore
implement the same interface, preventing drift and ensuring type safety.

Usage:
    from app.types.token_store import TokenStore

    # Annotate dependencies
    def get_token_store_dep() -> TokenStore: ...

    # Annotate implementations
    class TokenDAO(TokenStore): ...
    class FakeTokenStore(TokenStore): ...

    # Runtime checking
    assert isinstance(store, TokenStore)
"""

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class TokenStore(Protocol):
    """Protocol defining the token store interface."""

    async def upsert_token(self, token: Any) -> bool:
        """Store or update a token.

        Args:
            token: The token to store (ThirdPartyToken for real DAO)

        Returns:
            True if successful, False otherwise
        """
        ...

    async def get_token(
        self, user_id: str, provider: str, provider_sub: Optional[str] = None
    ) -> Optional[Any]:
        """Retrieve a token for the given user and provider.

        Args:
            user_id: User identifier
            provider: Provider name (e.g., 'spotify', 'google')
            provider_sub: Optional provider sub-identifier

        Returns:
            Token if found, None otherwise
        """
        ...

    async def delete_token(self, user_id: str, provider: str) -> bool:
        """Delete a token for the given user and provider.

        Args:
            user_id: User identifier
            provider: Provider name

        Returns:
            True if deleted, False if not found
        """
        ...

    async def has_any(self, user_id: str, provider: Optional[str] = None) -> bool:
        """Check if user has any tokens (optionally for a specific provider).

        Args:
            user_id: User identifier
            provider: Optional provider filter

        Returns:
            True if user has tokens, False otherwise
        """
        ...
