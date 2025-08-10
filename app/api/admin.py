from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps.user import get_current_user_id
from app.status import _admin_token
from app.analytics import get_metrics, cache_hit_rate, get_top_skills
from app.decisions import get_recent as decisions_recent, get_explain as decisions_get

router = APIRouter(tags=["admin"])


def _check_admin(token: str | None) -> None:
    _tok = _admin_token()
    if _tok and token != _tok:
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/admin/metrics")
async def admin_metrics(
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    _check_admin(token)
    m = get_metrics()
    return {"metrics": m, "cache_hit_rate": cache_hit_rate(), "top_skills": get_top_skills(10)}


@router.get("/admin/router/decisions")
async def admin_router_decisions(
    limit: int = Query(default=500, ge=1, le=1000),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    _check_admin(token)
    return {"items": decisions_recent(limit)}


@router.get("/admin/decisions/explain")
async def explain_decision(
    req_id: str,
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token)
    data = decisions_get(req_id)
    if not data:
        raise HTTPException(status_code=404, detail="not_found")
    return data


