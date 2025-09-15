"""Compatibility router exposing legacy endpoints with normalized shapes.

Lightweight stubs that call into existing modules when available but provide
stable fallback responses for tests and environments where integrations are
not present. Keep imports lazy to avoid heavy dependencies at import time.
"""

from __future__ import annotations

import inspect

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

router = APIRouter(tags=["Admin"])


class DeprecationRedirectResponse(RedirectResponse):
    """Custom redirect response that includes deprecation signaling headers.

    Used for legacy endpoint redirects to provide proper deprecation signaling
    with successor version information and sunset dates.
    """

    def __init__(
        self,
        url: str,
        *,
        successor_version: str | None = None,
        sunset_date: str | None = None,
        **kwargs,
    ):
        # Set default status to 308 (permanent redirect) if not specified
        kwargs.setdefault("status_code", 308)
        super().__init__(url, **kwargs)

        # Add deprecation signaling headers
        self.headers["Deprecation"] = "true"

        if sunset_date:
            self.headers["Sunset"] = sunset_date

        if successor_version:
            self.headers["Link"] = f'<{successor_version}>; rel="successor-version"'


@router.get("/whoami", deprecated=True)
async def whoami_compat(request: Request):
    """Redirect legacy /whoami to canonical /v1/whoami with 308 and Deprecation header."""
    resp = DeprecationRedirectResponse(
        url="/v1/whoami", successor_version="/v1/whoami", sunset_date="2025-12-31"
    )
    return resp


@router.get("/spotify/status", deprecated=True)
async def spotify_status_compat():
    """Call into Spotify integration status if available, else normalized 200."""

    def _attach_deprecation(
        resp: Response | JSONResponse | None,
        *,
        status: int | None = None,
        payload: dict | None = None,
    ) -> Response:
        if resp is not None:
            try:
                resp.headers["Deprecation"] = "true"
            except Exception:
                pass
            return resp
        return JSONResponse(
            payload or {"status": "ok"},
            status_code=status or 200,
            headers={"Deprecation": "true"},
        )

    try:
        from app.router.integrations import spotify_api

        maybe = spotify_api.spotify_status()
        res = await maybe if inspect.isawaitable(maybe) else maybe
        if isinstance(res, Response | JSONResponse):
            return _attach_deprecation(res)
        return _attach_deprecation(None, payload=res)
    except Exception:
        return _attach_deprecation(None, status=200, payload={"status": "ok"})


@router.post("/ask", deprecated=True)
async def ask_compat(request: Request):
    """Legacy root-level /ask endpoint.

    Behavior for tests and compat:
    - If the global router registry is unset -> 503 with code ROUTER_UNAVAILABLE
    - If the router raises -> 503 with code BACKEND_UNAVAILABLE
    - Otherwise, return the router's response (200)
    """
    # Try to fetch JSON body, but tolerate non-JSON
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Resolve the registered router
    try:
        from app.router.registry import get_router

        router = get_router()
    except Exception:
        return JSONResponse(
            {"code": "ROUTER_UNAVAILABLE", "message": "router not configured"},
            status_code=503,
            headers={"Deprecation": "true"},
        )

    # Call router; normalize any exception to 503 BACKEND_UNAVAILABLE
    try:
        result = await router.route_prompt(body if isinstance(body, dict) else {})
    except Exception:
        return JSONResponse(
            {"code": "BACKEND_UNAVAILABLE", "message": "backend unavailable"},
            status_code=503,
            headers={"Deprecation": "true"},
        )

    # Return JSON result; attach Deprecation header for compat
    if isinstance(result, Response | JSONResponse):
        try:
            result.headers.setdefault("Deprecation", "true")
        except Exception:
            pass
        return result
    return JSONResponse(
        result if isinstance(result, dict | list) else {"result": result},
        headers={"Deprecation": "true"},
    )


@router.get("/ask/replay/{rid}", deprecated=True)
async def ask_replay_compat(rid: str):
    """Legacy /ask/replay/{rid} endpoint - redirects to canonical /v1/ask/replay/{rid}.

    Only enabled when LEGACY_CHAT=1 environment variable is set.
    """
    import os

    from fastapi.responses import RedirectResponse

    # Check if legacy chat endpoints are enabled
    if os.getenv("LEGACY_CHAT", "").strip() not in {"1", "true", "yes", "on"}:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"error": "not_found", "message": "endpoint not available"},
            status_code=404,
        )

    # Perform 307 redirect to canonical endpoint
    resp = RedirectResponse(url=f"/v1/ask/replay/{rid}", status_code=307)
    try:
        resp.headers["Deprecation"] = "true"
    except Exception:
        pass
    return resp


@router.get("/google/status", deprecated=True)
async def google_status_compat():
    """Call into Google integration status if available, else normalized 200."""

    def _attach_deprecation(
        resp: Response | JSONResponse | None,
        *,
        status: int | None = None,
        payload: dict | None = None,
    ) -> Response:
        if resp is not None:
            try:
                resp.headers["Deprecation"] = "true"
            except Exception:
                pass
            return resp
        return JSONResponse(
            payload or {"status": "ok"},
            status_code=status or 200,
            headers={"Deprecation": "true"},
        )

    try:
        from app.router.integrations import google_api

        maybe = google_api.google_status()
        res = await maybe if inspect.isawaitable(maybe) else maybe
        if isinstance(res, Response | JSONResponse):
            return _attach_deprecation(res)
        return _attach_deprecation(None, payload=res)
    except Exception:
        return _attach_deprecation(None, status=200, payload={"status": "ok"})


@router.get("/health", deprecated=True)
async def health_compat(request: Request):
    """Redirect legacy /health to canonical /v1/health with 308 and Deprecation header."""
    resp = DeprecationRedirectResponse(
        url="/v1/health", successor_version="/v1/health", sunset_date="2025-12-31"
    )
    return resp


@router.get("/healthz", deprecated=True)
async def healthz_compat(request: Request):
    """Redirect legacy /healthz to canonical /v1/healthz with 308 and Deprecation header."""
    resp = DeprecationRedirectResponse(
        url="/v1/healthz", successor_version="/v1/healthz", sunset_date="2025-12-31"
    )
    return resp


@router.get("/status", deprecated=True)
async def status_compat(request: Request):
    """Redirect legacy /status to canonical /v1/status with 308 and Deprecation header."""
    resp = DeprecationRedirectResponse(
        url="/v1/status", successor_version="/v1/status", sunset_date="2025-12-31"
    )
    return resp


# Auth redirects moved to app/auth.py and app/router/auth_api.py as canonical sources
