from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Request

try:
    from app.deps.user import get_current_user_id, resolve_auth_source_conflict
except Exception:
    async def get_current_user_id(): return None
    def resolve_auth_source_conflict(*_a, **_kw): return ("unknown", False)

router = APIRouter(tags=["auth"])

@router.get("/whoami", name="whoami")
async def whoami(request: Request) -> Any:
    """Public whoami endpoint that always returns 200 without authentication."""
    # Try to get user info gracefully without requiring auth
    try:
        user_id = await get_current_user_id()
    except Exception:
        user_id = None

    try:
        source, conflict = await resolve_auth_source_conflict(request)
    except (TypeError, Exception):
        try:
            source, conflict = resolve_auth_source_conflict(request)  # sync fallback
        except Exception:
            source, conflict = ("unknown", False)

    authed = bool(user_id and user_id != "anon")
    return {"ok": True, "authenticated": authed, "user_id": user_id if authed else None,
            "source": source, "conflict": bool(conflict)}
