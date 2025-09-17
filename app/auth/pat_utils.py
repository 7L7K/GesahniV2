"""Personal Access Token (PAT) utilities for GesahniV2."""

import asyncio
import hashlib
from typing import Any


async def verify_pat_async(
    token: str, required_scopes: list[str] | None = None
) -> dict[str, Any] | None:
    """Async version of verify_pat for use in API handlers."""
    try:
        h = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
        rec = await _get_pat_by_hash(h)
        if not rec:
            return None
        if rec.get("revoked_at"):
            return None
        scopes = set(rec.get("scopes") or [])
        if required_scopes and not set(required_scopes).issubset(scopes):
            return None
        return rec
    except Exception:
        return None


def verify_pat(
    token: str, required_scopes: list[str] | None = None
) -> dict[str, Any] | None:
    """Synchronous version of verify_pat for backward compatibility."""
    try:
        h = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
        # Fetch synchronously via event loop since tests call this directly
        _ensure_loop()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In case an event loop is already running, fall back to None (not expected in unit)
                return None
            rec = loop.run_until_complete(_get_pat_by_hash(h))  # type: ignore[arg-type]
        except RuntimeError:
            rec = asyncio.run(_get_pat_by_hash(h))  # type: ignore[arg-type]
        if not rec:
            return None
        if rec.get("revoked_at"):
            return None
        scopes = set(rec.get("scopes") or [])
        if required_scopes and not set(required_scopes).issubset(scopes):
            return None
        return rec
    except Exception:
        return None


def _ensure_loop() -> None:
    """Ensure an asyncio event loop exists for synchronous PAT verification."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        # Only create a loop automatically in test contexts
        from .jwt_utils import _in_test_mode

        if _in_test_mode():
            asyncio.set_event_loop(asyncio.new_event_loop())


async def _get_pat_by_hash(token_hash: str) -> dict[str, Any] | None:
    """Get PAT record by token hash.

    This is a wrapper around the auth_store function to avoid import cycles.
    """
    try:
        from ..auth_store import get_pat_by_hash

        return await get_pat_by_hash(token_hash)
    except Exception:
        return None
