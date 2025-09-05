from __future__ import annotations

import os
from typing import Any
from dataclasses import asdict

import hashlib
import json
from datetime import UTC, datetime
from email.utils import format_datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from ..config_runtime import get_config
from ..deps.user import get_current_user_id, resolve_auth_source_conflict
from ..sessions_store import sessions_store
from ..user_store import user_store
from ..logging_config import req_id_var
from ..utils.cache_async import AsyncTTLCache, CachedError

try:
    from jose import jwt as jose_jwt
except ImportError:
    jose_jwt = None

router = APIRouter(tags=["Auth"])


def _to_dict(x) -> dict:
    """Convert various types to dict for safe access."""
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    if isinstance(x, BaseModel):
        return x.model_dump()
    if hasattr(x, '__dataclass_fields__'):  # dataclass
        return asdict(x)
    if hasattr(x, '__dict__'):
        return {k: v for k, v in vars(x).items() if not k.startswith('_')}
    return {"value": x}


_STATS_CACHE = AsyncTTLCache(ttl_seconds=5)


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/me")
async def me(request: Request, response: Response, user_id: str = Depends(get_current_user_id)) -> dict:
    is_auth = user_id != "anon"

    # Contract compliance: return 401 for anonymous users
    if not is_auth:
        from ..http_errors import unauthorized
        raise unauthorized(message="unauthorized")

    # Await user_store.get_stats(user_id)
    stats = None
    if is_auth:
        try:
            stats = await _STATS_CACHE.get(user_id, lambda: user_store.get_stats(user_id))
        except Exception:
            stats = None

    # Pass through _to_dict to get stats_dict
    stats_dict = _to_dict(stats)

    # Replace with safe dict access
    stats_result = {
        "login_count": stats_dict.get("login_count", 0),
        "request_count": stats_dict.get("request_count", 0),
        "last_login": stats_dict.get("last_login")
    }

    # Mixed auth source handling
    source, conflicted = resolve_auth_source_conflict(request)

    # Read access_token cookie and extract sub
    sub = None
    if jose_jwt is not None:
        access_token = request.cookies.get("access_token")
        if access_token:
            try:
                # Prefer unverified claims
                claims = jose_jwt.get_unverified_claims(access_token)
                sub = claims.get("sub")
            except Exception:
                try:
                    # Fallback: decode with ignore signature
                    payload = jose_jwt.decode(access_token, "ignore", options={"verify_signature": False})
                    sub = payload.get("sub")
                except Exception:
                    sub = None

    return {
        "user": {"id": user_id, "auth_source": source, "auth_conflict": conflicted},
        "stats": stats_result,
        "sub": sub
    }


# /v1/whoami is canonically served from app.api.auth; keep no duplicate here.


def _to_session_info(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_sid = os.getenv("CURRENT_SESSION_ID")
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        out.append(
            {
                "session_id": r.get("sid"),
                "device_id": r.get("did"),
                "device_name": r.get("device_name"),
                "created_at": r.get("created_at"),
                "last_seen_at": r.get("last_seen"),
                "current": bool(
                    (current_sid and r.get("sid") == current_sid) or i == 0
                ),
            }
        )
    return out


@router.get("/sessions")
async def sessions(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    legacy: int | None = Query(
        default=None,
        description="Return legacy wrapped shape when 1 (deprecated; TODO remove by 2026-01-31)",
    ),
) -> list[dict[str, Any]] | dict[str, Any]:
    if user_id == "anon":
        from ..http_errors import unauthorized

        raise unauthorized(message="authentication required", hint="login or include Authorization header")
    rows = await sessions_store.list_user_sessions(user_id)
    items = _to_session_info(rows)
    try:
        if str(legacy or "").strip() in {"1", "true", "yes"}:
            return {"items": items}
    except Exception:
        pass
    return items


@router.get("/sessions/paginated")
async def sessions_paginated(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    if user_id == "anon":
        from ..http_errors import unauthorized

        raise unauthorized(message="authentication required", hint="login or include Authorization header")
    rows = await sessions_store.list_user_sessions(user_id)
    start = 0
    try:
        if cursor is not None and str(cursor).strip() != "":
            start = max(0, int(cursor))
    except Exception:
        start = 0
    end = min(len(rows), start + int(limit))
    page = rows[start:end]
    next_cursor: str | None = str(end) if end < len(rows) else None
    return {"items": _to_session_info(page), "next_cursor": next_cursor}


@router.post("/sessions/{sid}/revoke")
async def revoke_session(
    sid: str, user_id: str = Depends(get_current_user_id)
) -> dict[str, str]:
    if user_id == "anon":
        from ..http_errors import unauthorized

        raise unauthorized(message="authentication required", hint="login or include Authorization header")
    await sessions_store.revoke_family(sid)
    return {"status": "ok"}


# /v1/pats is canonically served from app.api.auth; remove duplicate definitions here.


__all__ = ["router"]
