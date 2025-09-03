"""Simple registry for a global Router instance.

This module intentionally avoids importing heavy application modules so it
can be imported from low-level code without creating circular imports.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..bootstrap.router_contracts import Router


_router: Optional["Router"] = None


def set_router(router: "Router") -> None:
    """Set the global router instance.

    This is intended to be called once during application startup.
    """
    global _router
    _router = router


def get_router() -> "Router":
    """Return the registered router or raise RuntimeError if unset."""
    if _router is None:
        raise RuntimeError("Router has not been configured. Call set_router() first.")
    return _router


