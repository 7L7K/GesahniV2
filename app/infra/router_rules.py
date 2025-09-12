"""Router rules infrastructure component.

This module manages the global router rules cache.
Initialized from create_app() to avoid circular dependencies.
"""
from typing import Any

_router_rules_cache: dict[str, Any] | None = None


def init_router_rules_cache() -> None:
    """Initialize the global router rules cache.

    This function should be called from create_app() to initialize
    the router rules cache.
    """
    global _router_rules_cache
    if _router_rules_cache is None:
        from ..router.rules_loader import get_router_rules
        _router_rules_cache = get_router_rules()


def get_router_rules_cache() -> dict[str, Any]:
    """Get the global router rules cache.

    Returns:
        The global router rules cache

    Raises:
        RuntimeError: If the cache has not been initialized
    """
    if _router_rules_cache is None:
        raise RuntimeError("Router rules cache has not been initialized. Call init_router_rules_cache() first.")
    return _router_rules_cache


def invalidate_router_rules_cache() -> None:
    """Invalidate the router rules cache.

    This forces a reload on the next access.
    """
    global _router_rules_cache
    _router_rules_cache = None
