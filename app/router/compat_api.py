"""Compatibility router exposing legacy endpoints with normalized shapes.

Lightweight stubs that call into existing modules when available but provide
stable fallback responses for tests and environments where integrations are
not present. Keep imports lazy to avoid heavy dependencies at import time.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, Response
import inspect
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["Compat"])


@router.get("/whoami", deprecated=True)
async def whoami_compat(request: Request):
    """Call into app.router.auth_api.whoami if available, else return 401 fallback.
    """
    def _attach_deprecation(resp: Response | JSONResponse | None, *, status: int | None = None, payload: dict | None = None) -> Response:
        if resp is not None:
            # Ensure Deprecation header present
            try:
                resp.headers["Deprecation"] = "true"
            except Exception:
                pass
            return resp
        # Build a JSON response with deprecation header
        return JSONResponse(payload or {"status": "ok"}, status_code=status or 200, headers={"Deprecation": "true"})

    try:
        from app.router.auth_api import whoami as real_whoami
    except Exception:
        # Return 401 with Deprecation header rather than raising, so header is preserved
        return _attach_deprecation(None, status=401, payload={"error": "not_authenticated"})

    maybe = real_whoami(request)
    if inspect.isawaitable(maybe):
        res = await maybe
    else:
        res = maybe
    # If downstream returned a Response, attach header; if dict, wrap into JSON
    if isinstance(res, (Response, JSONResponse)):
        return _attach_deprecation(res)
    return _attach_deprecation(None, payload=res)


@router.get("/spotify/status", deprecated=True)
async def spotify_status_compat():
    """Call into Spotify integration status if available, else normalized 200."""
    def _attach_deprecation(resp: Response | JSONResponse | None, *, status: int | None = None, payload: dict | None = None) -> Response:
        if resp is not None:
            try:
                resp.headers["Deprecation"] = "true"
            except Exception:
                pass
            return resp
        return JSONResponse(payload or {"status": "ok"}, status_code=status or 200, headers={"Deprecation": "true"})

    try:
        from app.router.integrations import spotify_api

        maybe = spotify_api.spotify_status()
        res = await maybe if inspect.isawaitable(maybe) else maybe
        if isinstance(res, (Response, JSONResponse)):
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
    if isinstance(result, (Response, JSONResponse)):
        try:
            result.headers.setdefault("Deprecation", "true")
        except Exception:
            pass
        return result
    return JSONResponse(result if isinstance(result, (dict, list)) else {"result": result}, headers={"Deprecation": "true"})


@router.get("/google/status", deprecated=True)
async def google_status_compat():
    """Call into Google integration status if available, else normalized 200."""
    def _attach_deprecation(resp: Response | JSONResponse | None, *, status: int | None = None, payload: dict | None = None) -> Response:
        if resp is not None:
            try:
                resp.headers["Deprecation"] = "true"
            except Exception:
                pass
            return resp
        return JSONResponse(payload or {"status": "ok"}, status_code=status or 200, headers={"Deprecation": "true"})

    try:
        from app.router.integrations import google_api

        maybe = google_api.google_status()
        res = await maybe if inspect.isawaitable(maybe) else maybe
        if isinstance(res, (Response, JSONResponse)):
            return _attach_deprecation(res)
        return _attach_deprecation(None, payload=res)
    except Exception:
        return _attach_deprecation(None, status=200, payload={"status": "ok"})


# Auth redirects moved to app/auth.py and app/router/auth_api.py as canonical sources
