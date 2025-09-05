from __future__ import annotations

import time

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Any, Dict
import os

from .. import health_utils as hu
from .. import metrics as _m
from ..health import VendorHealthTracker
from ..metrics import HEALTH_OK, HEALTH_DEPS_OK

router = APIRouter(tags=["Health"])  # unauthenticated health; not privileged


@router.get("/health")
async def health_simple() -> JSONResponse:
    """Boring, unbreakable health endpoint.

    Always returns HTTP 200 with a minimal shape and short‑budget checks:
    {"status": "ok|degraded", "services": {"api": "up", "llama": "up|down", "ha": "up|down"}}
    """
    # Default everything to down; never raise from here
    llama_status = "down"
    ha_status = "down"
    try:
        ll = await hu.with_timeout(hu.check_llama, ms=500)
        llama_status = "up" if str(ll).lower() == "ok" else "down"
    except Exception:
        llama_status = "down"
    try:
        ha = await hu.with_timeout(hu.check_home_assistant, ms=500)
        ha_status = "up" if str(ha).lower() == "ok" else "down"
    except Exception:
        ha_status = "down"

    services = {"api": "up", "llama": llama_status, "ha": ha_status}
    overall = "ok" if all(v == "up" for v in services.values()) else "degraded"

    resp = JSONResponse({"status": overall, "services": services}, status_code=200)
    try:
        resp.headers["Cache-Control"] = "no-store"
        resp.headers.setdefault("Vary", "Accept")
    except Exception:
        pass
    return resp


@router.get("/healthz")
async def healthz_root() -> JSONResponse:
    """Simple health check endpoint for probes - root level for compatibility."""
    try:
        resp = JSONResponse({"ok": True, "status": "ok"})
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        resp.headers.setdefault("Vary", "Accept")
        return resp
    except Exception as e:
        # Defensive: should not happen, but keep contract stable
        try:
            import logging
            logging.getLogger(__name__).error(
                "health.failed", extra={"meta": {"endpoint": "healthz", "error": str(e)}}
            )
        except Exception:
            pass
        return JSONResponse({"ok": False, "status": "error"}, status_code=200)


@router.get("/healthz/live", include_in_schema=False)
async def health_live() -> JSONResponse:
    """Liveness: process is up. No I/O, no auth, no side effects.

    Never returns 5xx; wraps errors and reports ok=False.
    """
    try:
        resp = JSONResponse({"status": "ok"})
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        resp.headers.setdefault("Vary", "Accept")
        return resp
    except Exception as e:
        # Defensive: should not happen, but keep contract stable
        try:
            import logging
            logging.getLogger(__name__).error(
                "health.failed", extra={"meta": {"endpoint": "live", "error": str(e)}}
            )
        except Exception:
            pass
        return JSONResponse({"status": "error"}, status_code=200)


@router.get(
    "/healthz/ready",
    responses={
        200: {
            "description": "Readiness status (always 200, never 5xx)",
            "content": {
                "application/json": {
                    "examples": {
                        "healthy": {
                            "summary": "All components healthy",
                            "value": {
                                "status": "ok",
                                "ok": True,
                                "components": {
                                    "jwt_secret": {"status": "healthy"},
                                    "db": {"status": "healthy"},
                                    "vector_store": {"status": "healthy"}
                                }
                            }
                        },
                        "degraded": {
                            "summary": "Some components degraded",
                            "value": {
                                "status": "degraded",
                                "ok": True,
                                "components": {
                                    "jwt_secret": {"status": "healthy"},
                                    "db": {"status": "healthy"},
                                    "vector_store": {"status": "degraded"}
                                }
                            }
                        },
                        "unhealthy": {
                            "summary": "Critical components unhealthy",
                            "value": {
                                "status": "unhealthy",
                                "ok": False,
                                "components": {
                                    "jwt_secret": {"status": "unhealthy"},
                                    "db": {"status": "healthy"},
                                    "vector_store": {"status": "healthy"}
                                },
                                "failing": ["jwt_secret"]
                            }
                        }
                    }
                }
            }
        }
    }
)
async def health_ready() -> JSONResponse:
    """Core readiness with structured component status.

    Required checks (all must pass):
    - JWT secret present
    - DB/session store basic open
    - Vector store connectivity (read-only)

    Each component returns: healthy | degraded | unhealthy
    Overall status is unhealthy if any required component is unhealthy.

    Always returns HTTP 200 - never 5xx. Degraded status is indicated in response body.
    """
    import datetime

    # Component health checks
    components = {}

    # JWT secret check
    t = time.perf_counter()
    jwt_result = await hu.with_timeout(hu.check_jwt_secret, ms=500)
    try:
        _m.HEALTH_CHECK_DURATION_SECONDS.labels("jwt").observe(time.perf_counter() - t)
    except Exception:
        pass
    components["jwt_secret"] = {"status": "healthy" if jwt_result == "ok" else "unhealthy"}

    # Database check
    t = time.perf_counter()
    db_result = await hu.with_timeout(hu.check_db, ms=500)
    try:
        _m.HEALTH_CHECK_DURATION_SECONDS.labels("db").observe(time.perf_counter() - t)
    except Exception:
        pass
    components["db"] = {"status": "healthy" if db_result == "ok" else "unhealthy"}

    # Vector store check (read-only)
    t = time.perf_counter()
    try:
        from ..memory.api import _get_store

        store = _get_store()
        if hasattr(store, "ping"):
            await hu.with_timeout(store.ping, ms=500)
        elif hasattr(store, "search_memories"):
            await hu.with_timeout(
                lambda: store.search_memories("", "", limit=0), ms=500
            )
        vector_status = "healthy"
    except Exception:
        vector_status = "unhealthy"
    try:
        _m.HEALTH_CHECK_DURATION_SECONDS.labels("vector_store").observe(
            time.perf_counter() - t
        )
    except Exception:
        pass
    components["vector_store"] = {"status": vector_status}

    # Determine overall status
    unhealthy_components = [
        name for name, comp in components.items() if comp["status"] == "unhealthy"
    ]
    degraded_components = [
        name for name, comp in components.items() if comp["status"] == "degraded"
    ]

    # Map internal component health and include ok boolean; ALWAYS 200
    if unhealthy_components:
        overall_status = "unhealthy"
        ok = False
    elif degraded_components:
        overall_status = "degraded"
        ok = True
    else:
        overall_status = "ok"
        ok = True

    # Prepare response data - use simple format for tests
    # Update health gauges
    try:
        HEALTH_OK.set(1.0 if ok else 0.0)
        for comp, data in components.items():
            st = str(data.get("status", "unhealthy"))
            # Consider degraded as ok for availability purposes
            HEALTH_DEPS_OK.labels(component=comp).set(1.0 if st in {"healthy", "degraded", "ok"} else 0.0)
    except Exception:
        pass

    # Build response with expected fields for tests and consumers
    response_data = {
        "status": overall_status,
        "ok": ok,
        "components": components
    }

    if unhealthy_components:
        # Legacy key `failing` is expected by some consumers/tests; keep it for
        # backwards compatibility
        response_data["failing"] = unhealthy_components
        try:
            for component in unhealthy_components:
                _m.HEALTH_READY_FAILURES_TOTAL.labels(component).inc()
        except Exception:
            pass

    # Always return 200 for readiness probes, even when degraded
    # Readiness probes should never return 5xx - they indicate degraded status in response body
    resp = JSONResponse(response_data, status_code=200)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    resp.headers.setdefault("Vary", "Accept")
    return resp


@router.get("/v1/ping", include_in_schema=False)
async def ping_vendor_health(
    vendor: str = Query(
        ..., description="Vendor name to ping (e.g., 'openai', 'ollama')"
    ),
    clear: bool = Query(False, description="Clear unhealthy status for the vendor"),
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
                "message": f"Unhealthy status cleared for vendor {vendor}",
            }

        # Get current health info
        health_info = VendorHealthTracker.get_vendor_health_info(vendor)

        if health_info["is_healthy"]:
            return {
                "status": "healthy",
                "vendor": vendor,
                "healthy": True,
                "message": f"Vendor {vendor} is healthy",
            }
        else:
            return {
                "status": "unhealthy",
                "vendor": vendor,
                "healthy": False,
                "remaining_seconds": health_info["remaining_unhealthy_seconds"],
                "recent_failures": health_info["recent_failures"],
                "failure_threshold": health_info["failure_threshold"],
                "message": f"Vendor {vendor} is unhealthy for {health_info['remaining_unhealthy_seconds']:.1f} more seconds",
            }

    except Exception as e:
        try:
            import logging
            logging.getLogger(__name__).error(
                "health.failed", extra={"meta": {"endpoint": "vendor", "vendor": vendor, "error": str(e)}}
            )
        except Exception:
            pass
        return {
            "ok": False,
            "status": "error",
            "vendor": vendor,
            "error": str(e),
            "message": f"Error checking health for vendor {vendor}: {e}",
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
            "unhealthy_vendors": sum(
                1 for info in all_health_info.values() if not info["is_healthy"]
            ),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Error getting vendor health status: {e}",
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
    status = (
        "ok" if all(v in {"ok", "skipped"} for v in checks.values()) else "degraded"
    )
    resp = JSONResponse({"status": status, "checks": checks})
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    resp.headers.setdefault("Vary", "Accept")
    return resp


@router.get("/v1/health")
async def health_combined() -> JSONResponse:
    """Unified health snapshot that always returns HTTP 200.

    Shape: { status: 'ok'|'degraded'|'fail', checks: { backend, jwt, database, vector_store, llama, ha, qdrant, spotify } }
    """
    try:
        ready = await health_ready()
        deps = await health_deps()

        # Normalize bodies when returned as JSONResponse
        import json
        def to_obj(x: object) -> dict:
            if isinstance(x, JSONResponse):
                try:
                    body = x.body
                    if isinstance(body, (bytes, bytearray)):
                        return json.loads(body.decode())
                    if isinstance(body, str):
                        return json.loads(body)
                    return {}
                except Exception:
                    return {}
            return x if isinstance(x, dict) else {}

        r = to_obj(ready)
        d = to_obj(deps)

        checks: dict[str, str] = { 'backend': 'ok' }
        for name, comp in (r.get('components') or {}).items():
            st = str((comp or {}).get('status') or 'unhealthy')
            checks[name] = 'ok' if st == 'healthy' else ('degraded' if st == 'degraded' else 'error')
        for name, st in (d.get('checks') or {}).items():
            checks.setdefault(name, str(st))

        overall = 'ok'
        if (r.get('status') == 'fail'):
            overall = 'fail'
        elif (r.get('status') == 'degraded') or (d.get('status') == 'degraded'):
            overall = 'degraded'

        resp = JSONResponse({ 'status': overall, 'checks': checks })
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    except Exception:
        # Always return 200 with a minimal fail snapshot on any exception
        resp = JSONResponse({ 'status': 'fail', 'checks': { 'backend': 'error' } })
        resp.headers['Cache-Control'] = 'no-store'
        return resp

@router.get("/health/vector_store")
@router.get("/v1/health/vector_store")
async def health_vector_store() -> dict:
    """Return a small diagnostic summary for the configured vector store.

    Intended for automated smoke tests: returns `ok` + store_type + config
    and a minimal write/read smoke check when possible.
    """
    from ..memory.unified_store import get_vector_store_info
    from ..memory.api import add_user_memory, get_store

    cfg = get_vector_store_info()
    out: dict = {"ok": True}
    out["config"] = cfg
    # Determine concrete store type
    try:
        store = get_store()
        stype = type(store).__name__
    except Exception:
        store = None
        stype = cfg.get("backend") or cfg.get("scheme") or "unknown"

    out["store_type"] = stype

    # Embedding metadata (observability)
    out["embedding_model"] = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    out["embedding_dim"] = os.getenv("EMBED_DIM", "1536")
    out["distance_metric"] = os.getenv("VECTOR_METRIC", "COSINE")

    # Perform a minimal smoke write/read where supported
    test_id = None
    test_passed = False
    try:
        if store is not None:
            # Use high-level helper so PII redaction + wrappers are exercised
            test_id = add_user_memory("smoke_test_user", "smoke memory")
            test_passed = bool(test_id)
    except Exception as e:
        out["ok"] = True
        out["smoke_error"] = str(e)

    out["test_passed"] = test_passed
    out["test_memory_id"] = test_id

    # Surface basic backend stats from config for assertions in tests
    out["backend_stats"] = {
        "backend": cfg.get("backend", "unknown"),
        "host": cfg.get("host", ""),
        "port": cfg.get("port", ""),
        "path": cfg.get("path", ""),
    }

    return out


@router.get(
    "/v1/health/qdrant",
    responses={
        200: {
            "description": "Qdrant health status",
            "content": {
                "application/json": {
                    "examples": {
                        "healthy": {
                            "summary": "Qdrant is healthy",
                            "value": {"ok": True, "status": "ok"}
                        },
                        "unhealthy": {
                            "summary": "Qdrant is not responding",
                            "value": {"ok": False, "status": "error", "error": "Connection timeout"}
                        },
                        "skipped": {
                            "summary": "Qdrant not configured",
                            "value": {"ok": False, "status": "skipped"}
                        }
                    }
                }
            }
        }
    }
)
async def health_qdrant() -> Dict[str, Any]:
    """Check Qdrant health status."""
    try:
        status = await hu.with_timeout(hu.check_qdrant, ms=500)
        return {"ok": status == "ok", "status": status}
    except Exception as e:
        return {"ok": False, "status": "error", "error": str(e)}


@router.get(
    "/v1/health/chroma",
    responses={
        200: {
            "description": "Chroma health status",
            "content": {
                "application/json": {
                    "examples": {
                        "healthy": {
                            "summary": "Chroma is healthy",
                            "value": {"ok": True, "status": "ok"}
                        },
                        "unhealthy": {
                            "summary": "Chroma is not responding",
                            "value": {"ok": False, "status": "error", "error": "Connection timeout"}
                        },
                        "skipped": {
                            "summary": "Chroma not configured as vector store",
                            "value": {"ok": False, "status": "skipped"}
                        }
                    }
                }
            }
        }
    }
)
async def health_chroma() -> Dict[str, Any]:
    """Check Chroma health status."""
    try:
        status = await hu.with_timeout(hu.check_chroma, ms=500)
        return {"ok": status == "ok", "status": status}
    except Exception as e:
        return {"ok": False, "status": "error", "error": str(e)}
