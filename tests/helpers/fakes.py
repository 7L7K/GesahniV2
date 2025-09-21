"""
Fake implementations for testing.
"""

from typing import Dict, List, Optional, Tuple
from app.models.third_party_tokens import ThirdPartyToken
from app.types.token_store import TokenStore


class FakeTokenStore(TokenStore):
    """Fake token store for testing that tracks saved tokens."""

    def __init__(self, preloaded_tokens: Optional[Dict[Tuple[str, str], ThirdPartyToken]] = None):
        """Initialize fake store with optional preloaded tokens.

        Args:
            preloaded_tokens: Dict mapping (user_id, provider) tuples to ThirdPartyToken objects.
                             Useful for testing scenarios where tokens already exist.
        """
        self.tokens: Dict[Tuple[str, str], ThirdPartyToken] = preloaded_tokens or {}
        self.preloaded_tokens = set(self.tokens.keys())  # Track which tokens were preloaded
        # Initialize saved list with preloaded tokens so all_saved includes them
        self.saved: List[ThirdPartyToken] = list(self.tokens.values())

    async def upsert_token(self, token: ThirdPartyToken) -> bool:
        """Store a token and track it for assertions."""
        key = (token.user_id, token.provider)
        self.saved.append(token)
        self.tokens[key] = token
        return True

    async def get_token(
        self, user_id: str, provider: str, provider_sub: str | None = None
    ) -> ThirdPartyToken | None:
        """Retrieve a token by user_id and provider."""
        key = (user_id, provider)
        return self.tokens.get(key)

    async def delete_token(self, user_id: str, provider: str) -> bool:
        """Delete a token (for completeness)."""
        key = (user_id, provider)
        if key in self.tokens:
            del self.tokens[key]
            return True
        return False

    async def has_any(self, user_id: str, provider: str | None = None) -> bool:
        """Check if user has any tokens (optionally for a specific provider)."""
        if provider:
            return (user_id, provider) in self.tokens
        return any(uid == user_id for (uid, _p) in self.tokens.keys())

    @property
    def newly_saved(self) -> List[ThirdPartyToken]:
        """Get only the tokens saved during this test (excludes preloaded tokens)."""
        return [token for token in self.saved
                if (token.user_id, token.provider) not in self.preloaded_tokens]

    @property
    def all_saved(self) -> List[ThirdPartyToken]:
        """Get all saved tokens (including preloaded ones)."""
        return self.saved.copy()

    def clear(self):
        """Clear all stored tokens (useful for test cleanup)."""
        self.tokens.clear()
        self.preloaded_tokens.clear()
        self.saved.clear()
