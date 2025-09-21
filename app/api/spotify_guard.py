"""
Guard against legacy test patches that bypass dependency injection.

This module prevents accidental resurrection of monkey patches that directly
modify app.api.spotify.upsert_token and app.api.spotify.get_token. Such patches
bypass FastAPI's dependency injection system and make tests brittle.

Instead, use dependency injection overrides:
    app.dependency_overrides[get_token_store_dep] = lambda: fake_store

This ensures tests work with the real DI system and catch integration issues.
"""

from typing import Any


def __getattr__(name: str) -> Any:
    """Prevent access to legacy patch targets."""
    if name in {"upsert_token", "get_token"}:
        raise AttributeError(
            "Legacy test seam removed. Use DI override of get_token_store_dep with a fake store. "
            "See tests/INTEGRATION_TESTING.md for examples."
        )
    raise AttributeError(name)
