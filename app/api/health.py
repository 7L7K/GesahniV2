from __future__ import annotations

import os
from typing import Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import health_utils as hu


router = APIRouter(tags=["Health"])  # unauthenticated health; not privileged


@router.get("/healthz/live", include_in_schema=False)
async def health_live() -> Dict[str, str]:
    """Liveness: process is up. No I/O, no auth, no side effects."""
    return {"status": "ok"}


@router.get("/healthz/ready", include_in_schema=False)
async def health_ready() -> Dict[str, object]:
    """Core readiness only.

    Required checks (all must pass):
    - JWT secret present
    - DB/session store basic open
    Each check is timeboxed (500ms).
    """
    failing: List[str] = []

    jwt = await hu.with_timeout(hu.check_jwt_secret, ms=500)
    if jwt != "ok":
        failing.append("jwt")

    db = await hu.with_timeout(hu.check_db, ms=500)
    if db != "ok":
        failing.append("db")

    if failing:
        return JSONResponse({"status": "fail", "failing": failing}, status_code=503)
    return {"status": "ok"}


@router.get("/healthz/deps", include_in_schema=False)
async def health_deps() -> Dict[str, object]:
    """Optional dependencies (non-blocking for readiness).

    Maps each dependency to "ok" | "error" | "skipped". Overall status is
    "degraded" iff any check is "error"; otherwise "ok".
    """
    checks = {
        "backend": "ok",
        "llama": await hu.with_timeout(hu.check_llama, ms=500),
        "ha": await hu.with_timeout(hu.check_home_assistant, ms=500),
        "qdrant": await hu.with_timeout(hu.check_qdrant, ms=500),
        "spotify": await hu.with_timeout(hu.check_spotify, ms=500),
    }
    status = "ok" if all(v in {"ok", "skipped"} for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}


