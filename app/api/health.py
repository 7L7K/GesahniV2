from __future__ import annotations

import time

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .. import health_utils as hu
from .. import metrics as _m
from ..health import VendorHealthTracker

router = APIRouter(tags=["Health"])  # unauthenticated health; not privileged


@router.get("/healthz/live", include_in_schema=False)
async def health_live() -> dict[str, str]:
    """Liveness: process is up. No I/O, no auth, no side effects."""
    resp = JSONResponse({"status": "ok"})
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    resp.headers.setdefault("Vary", "Accept")
    return resp


@router.get("/healthz/ready", include_in_schema=False)
async def health_ready() -> dict[str, object]:
    """Core readiness with structured component status.

    Required checks (all must pass):
    - JWT secret present
    - DB/session store basic open
    - Vector store connectivity (read-only)

    Each component returns: healthy | degraded | unhealthy
    Overall status is unhealthy if any required component is unhealthy.
    """
    import datetime

    # Component health checks
    components = {}

    # JWT secret check
    t = time.perf_counter()
    jwt_result = await hu.with_timeout(hu.check_jwt_secret, ms=500)
    try: _m.HEALTH_CHECK_DURATION_SECONDS.labels("jwt").observe(time.perf_counter() - t)
    except Exception: pass
    components["jwt"] = {"status": "healthy" if jwt_result == "ok" else "unhealthy"}

    # Database check
    t = time.perf_counter()
    db_result = await hu.with_timeout(hu.check_db, ms=500)
    try: _m.HEALTH_CHECK_DURATION_SECONDS.labels("db").observe(time.perf_counter() - t)
    except Exception: pass
    components["database"] = {"status": "healthy" if db_result == "ok" else "unhealthy"}

    # Vector store check (read-only)
    t = time.perf_counter()
    try:
        from ..memory.api import _get_store
        store = _get_store()
        if hasattr(store, 'ping'):
            await hu.with_timeout(store.ping, ms=500)
        elif hasattr(store, 'search_memories'):
            await hu.with_timeout(lambda: store.search_memories("", "", limit=0), ms=500)
        vector_status = "healthy"
    except Exception:
        vector_status = "unhealthy"
    try: _m.HEALTH_CHECK_DURATION_SECONDS.labels("vector_store").observe(time.perf_counter() - t)
    except Exception: pass
    components["vector_store"] = {"status": vector_status}

    # Determine overall status
    unhealthy_components = [name for name, comp in components.items() if comp["status"] == "unhealthy"]
    degraded_components = [name for name, comp in components.items() if comp["status"] == "degraded"]

    if unhealthy_components:
        overall_status = "unhealthy"
        status_code = 503
    elif degraded_components:
        overall_status = "degraded"
        status_code = 200
    else:
        overall_status = "healthy"
        status_code = 200

    # Prepare response data
    response_data = {
        "status": overall_status,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "components": components
    }

    if unhealthy_components:
        response_data["unhealthy_components"] = unhealthy_components
        try:
            for component in unhealthy_components:
                _m.HEALTH_READY_FAILURES_TOTAL.labels(component).inc()
        except Exception:
            pass

    if degraded_components:
        response_data["degraded_components"] = degraded_components

    resp = JSONResponse(response_data, status_code=status_code)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    resp.headers.setdefault("Vary", "Accept")
    return resp


@router.get("/v1/ping", include_in_schema=False)
async def ping_vendor_health(
    vendor: str = Query(..., description="Vendor name to ping (e.g., 'openai', 'ollama')"),
    clear: bool = Query(False, description="Clear unhealthy status for the vendor")
) -> dict[str, object]:
    """
    Lightweight ping endpoint to check/clear vendor health status.

    This endpoint provides a quick way to:
    1. Check if a vendor is marked unhealthy by the eager health gating system
    2. Clear an unhealthy status to allow the vendor to be tried again

    Args:
        vendor: The vendor name to check/clear
        clear: If True, clears the unhealthy status for the vendor

    Returns:
        Dictionary with vendor health status and metadata
    """
    try:
        if clear:
            VendorHealthTracker.clear_vendor_health(vendor)
            return {
                "status": "cleared",
                "vendor": vendor,
                "message": f"Unhealthy status cleared for vendor {vendor}"
            }

        # Get current health info
        health_info = VendorHealthTracker.get_vendor_health_info(vendor)

        if health_info["is_healthy"]:
            return {
                "status": "healthy",
                "vendor": vendor,
                "healthy": True,
                "message": f"Vendor {vendor} is healthy"
            }
        else:
            return {
                "status": "unhealthy",
                "vendor": vendor,
                "healthy": False,
                "remaining_seconds": health_info["remaining_unhealthy_seconds"],
                "recent_failures": health_info["recent_failures"],
                "failure_threshold": health_info["failure_threshold"],
                "message": f"Vendor {vendor} is unhealthy for {health_info['remaining_unhealthy_seconds']:.1f} more seconds"
            }

    except Exception as e:
        return {
            "status": "error",
            "vendor": vendor,
            "error": str(e),
            "message": f"Error checking health for vendor {vendor}: {e}"
        }


@router.get("/v1/vendor-health", include_in_schema=False)
async def get_vendor_health_status() -> dict[str, object]:
    """
    Get health status for all vendors being tracked by the eager health gating system.

    Returns:
        Dictionary with health information for all tracked vendors
    """
    try:
        all_health_info = VendorHealthTracker.get_all_vendor_health_info()

        return {
            "status": "ok",
            "vendors": all_health_info,
            "total_vendors": len(all_health_info),
            "unhealthy_vendors": sum(1 for info in all_health_info.values() if not info["is_healthy"])
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Error getting vendor health status: {e}"
        }


@router.get("/healthz/deps", include_in_schema=False)
async def health_deps() -> dict[str, object]:
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


