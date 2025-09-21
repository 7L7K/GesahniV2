"""
FastAPI dependencies for token store services.

These dependencies provide token store instances for FastAPI routes and endpoints.
"""

from __future__ import annotations

from .auth_store_tokens import TokenDAO
from .factories import make_token_store
from .types.token_store import TokenStore


def get_token_store_dep() -> TokenStore:
    """
    FastAPI dependency that returns a TokenDAO instance.

    This dependency creates a new TokenDAO instance for each request.
    Use this in FastAPI route dependencies.

    Usage:
        @router.get("/v1/spotify/status")
        async def spotify_status(store = Depends(get_token_store_dep)):
            ...
    """
    return make_token_store()


__all__ = ["get_token_store_dep"]
