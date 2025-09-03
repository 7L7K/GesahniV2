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


def attach_all(app) -> None:
    """Attach compatibility and lightweight stub routers under the `/v1` prefix.

    Each import is best-effort: missing modules are skipped to avoid import-time
    failures in test environments.
    """
    # Alias router for many small compatibility shims (include first so it
    # can override one-off compat handlers when present).
    try:
        from .alias_api import router as alias_router

        app.include_router(alias_router, prefix="/v1")
    except Exception:
        pass

    # Compatibility router (whoami, spotify/google status)
    try:
        from .compat_api import router as compat_router

        app.include_router(compat_router, prefix="/v1")
    except Exception:
        # Best-effort: do not fail if compat router unavailable
        pass

    # Stub routers replaced by alias router entries; individual stub modules
    # removed to reduce maintenance. Specific integrations should be imported
    # lazily from `alias_api` when available.


