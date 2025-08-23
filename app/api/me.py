from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..config_runtime import get_config
from ..deps.user import get_current_user_id
from ..sessions_store import sessions_store
from ..user_store import user_store

router = APIRouter(tags=["Auth"])


@router.get("/me")
async def me(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    is_auth = user_id != "anon"
    stats = await user_store.get_stats(user_id) if is_auth else None

    cfg = get_config()
    flags = {
        "retrieval_pipeline": os.getenv("RETRIEVAL_PIPELINE", "0").lower()
        in {"1", "true", "yes"},
        "use_hosted_rerank": os.getenv("RETRIEVE_USE_HOSTED_CE", "0").lower()
        in {"1", "true", "yes"},
        "debug_model_routing": os.getenv("DEBUG_MODEL_ROUTING", "0").lower()
        in {"1", "true", "yes"},
        "ablation_flags": sorted(list(cfg.obs.ablation_flags)),
        "trace_sample_rate": cfg.obs.trace_sample_rate,
    }

    profile = {
        "user_id": user_id,
        "login_count": (stats or {}).get("login_count", 0),
        "last_login": (stats or {}).get("last_login"),
        "request_count": (stats or {}).get("request_count", 0),
    }
    return {"is_authenticated": is_auth, "profile": profile, "flags": flags}


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
        raise HTTPException(status_code=401, detail="Unauthorized")
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
        raise HTTPException(status_code=401, detail="Unauthorized")
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
        raise HTTPException(status_code=401, detail="Unauthorized")
    await sessions_store.revoke_family(sid)
    return {"status": "ok"}


# /v1/pats is canonically served from app.api.auth; remove duplicate definitions here.


__all__ = ["router"]
