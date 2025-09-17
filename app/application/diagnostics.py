from __future__ import annotations

import hashlib
import json
import logging
import os

from fastapi import APIRouter, FastAPI, Query

from app.diagnostics.startup_probe import probe
from app.diagnostics.state import (
    events,
    get_snapshot,
    import_timings,
    record_event,
    router_calls,
    set_snapshot,
)

logger = logging.getLogger(__name__)


def prepare_snapshots(app: FastAPI, *, debug: bool) -> None:
    """Capture diagnostic snapshots once routing and middleware wiring completes."""
    set_snapshot("after", probe(app))
    if debug:
        record_event("wiring-complete", "routers+middleware registered")


def build_diagnostics_router(*, debug: bool) -> APIRouter:
    """Create the diagnostic router mounted at ``/__diag`` paths."""
    diag = APIRouter()

    if debug:
        record_event("diag-router", "diagnostic router constructed")

    @diag.get("/__diag/startup", include_in_schema=False)
    async def __diag_startup(phase: str = Query(default="after")):
        return get_snapshot("before" if phase == "before" else "after")

    @diag.get("/__diag/events", include_in_schema=False)
    async def __diag_events():
        return {
            "events": events(),
            "router_calls": router_calls(),
            "import_timings": import_timings(),
        }

    @diag.get("/__diag/verify", include_in_schema=False)
    async def __diag_verify():
        snap = get_snapshot("after")
        routes = snap.get("routes", [])
        mids = [m.get("class_name") for m in snap.get("middlewares", [])]
        paths = [r.get("path") for r in routes]
        checks = []

        def add(name: str, ok: bool, details: str = "") -> None:
            checks.append({"name": name, "ok": bool(ok), "details": details})

        try:
            cors_required = bool(
                (
                    os.getenv("CORS_ORIGINS") or os.getenv("CORS_ALLOW_ORIGINS") or ""
                ).strip()
            )
        except Exception:  # pragma: no cover - defensive for odd env values
            cors_required = False

        cors_count = mids.count("CORSMiddleware")
        if cors_required:
            add("CORS present once", cors_count == 1, f"count={cors_count}")
        else:
            add(
                "CORS omitted in proxy/same-origin",
                cors_count == 0,
                f"count={cors_count}",
            )

        if "CSRFMiddleware" in mids and "CORSMiddleware" in mids:
            add(
                "CSRF before CORS",
                mids.index("CSRFMiddleware") < mids.index("CORSMiddleware"),
                f"order={mids}",
            )
        else:
            add("CSRF ordering skipped", True, "CSRF or CORS missing")

        add("has /v1/auth/whoami", "/v1/auth/whoami" in paths)
        add("has health", ("/health" in paths) or ("/v1/health" in paths))
        dup = sorted({p for p in paths if paths.count(p) > 1})
        add("no duplicate paths", not dup, f"dups={dup}")

        passed = all(check["ok"] for check in checks)
        return {"phase": snap.get("phase", "after"), "passed": passed, "checks": checks}

    @diag.get("/__diag/fingerprint", include_in_schema=False)
    async def __diag_fingerprint():
        """Generate a stable fingerprint of the application state for regression detection."""
        snap = get_snapshot("after")
        routes = snap.get("routes", [])
        mids = snap.get("middlewares", [])

        route_info = []
        for route in sorted(routes, key=lambda x: x.get("path", "")):
            route_info.append(
                {
                    "path": route.get("path", ""),
                    "methods": sorted(route.get("methods", [])),
                    "name": route.get("name", ""),
                }
            )

        middleware_info = []
        for middleware in mids:
            middleware_info.append(
                {
                    "class_name": middleware.get("class_name", ""),
                    "name": middleware.get("name", ""),
                }
            )

        fingerprint_data = {
            "routes": route_info,
            "middlewares": middleware_info,
            "phase": snap.get("phase", "after"),
        }

        stable_json = json.dumps(
            fingerprint_data, sort_keys=True, separators=(",", ":")
        )
        fingerprint = hashlib.sha256(stable_json.encode("utf-8")).hexdigest()[:16]

        return {
            "fingerprint": fingerprint,
            "data": fingerprint_data,
            "generated_at": snap.get("timestamp", "unknown"),
        }

    logger.info("DEBUG: Diagnostic router constructed with %d routes", len(diag.routes))
    return diag


__all__ = ["prepare_snapshots", "build_diagnostics_router"]
