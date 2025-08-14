from __future__ import annotations

import os
from typing import Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import time
from .. import metrics as _m

from .. import health_utils as hu


router = APIRouter(tags=["Health"])  # unauthenticated health; not privileged


@router.get("/healthz/live", include_in_schema=False)
async def health_live() -> Dict[str, str]:
    """Liveness: process is up. No I/O, no auth, no side effects."""
    resp = JSONResponse({"status": "ok"})
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    resp.headers.setdefault("Vary", "Accept")
    return resp


@router.get("/healthz/ready", include_in_schema=False)
async def health_ready() -> Dict[str, object]:
    """Core readiness only.

    Required checks (all must pass):
    - JWT secret present
    - DB/session store basic open
    Each check is timeboxed (500ms).
    """
    failing: List[str] = []

    t = time.perf_counter()
    jwt = await hu.with_timeout(hu.check_jwt_secret, ms=500)
    try: _m.HEALTH_CHECK_DURATION_SECONDS.labels("jwt").observe(time.perf_counter() - t)
    except Exception: pass
    if jwt != "ok":
        failing.append("jwt")

    t = time.perf_counter()
    db = await hu.with_timeout(hu.check_db, ms=500)
    try: _m.HEALTH_CHECK_DURATION_SECONDS.labels("db").observe(time.perf_counter() - t)
    except Exception: pass
    if db != "ok":
        failing.append("db")

    if failing:
        try:
            for r in failing:
                _m.HEALTH_READY_FAILURES_TOTAL.labels(r).inc()
        except Exception:
            pass
        resp = JSONResponse({"status": "fail", "failing": failing}, status_code=503)
        resp.headers["Cache-Control"] = "no-store"; resp.headers["Pragma"] = "no-cache"; resp.headers.setdefault("Vary","Accept")
        return resp
    resp = JSONResponse({"status": "ok"})
    resp.headers["Cache-Control"] = "no-store"; resp.headers["Pragma"] = "no-cache"; resp.headers.setdefault("Vary","Accept")
    return resp


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
    resp = JSONResponse({"status": status, "checks": checks})
    resp.headers["Cache-Control"] = "no-store"; resp.headers["Pragma"] = "no-cache"; resp.headers.setdefault("Vary","Accept")
    return resp


