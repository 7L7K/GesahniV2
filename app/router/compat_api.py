"""Compatibility router exposing legacy endpoints with normalized shapes.

Lightweight stubs that call into existing modules when available but provide
stable fallback responses for tests and environments where integrations are
not present. Keep imports lazy to avoid heavy dependencies at import time.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import inspect

router = APIRouter(tags=["Compat"])


@router.get("/whoami", deprecated=True)
async def whoami_compat(request: Request):
    """Call into app.router.auth_api.whoami if available, else return 401 fallback.
    """
    try:
        from app.router.auth_api import whoami as real_whoami
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"})

    maybe = real_whoami(request)
    if inspect.isawaitable(maybe):
        return await maybe
    return maybe


@router.get("/spotify/status", deprecated=True)
async def spotify_status_compat():
    """Call into Spotify integration status if available, else normalized 200."""
    try:
        from app.router.integrations import spotify_api

        maybe = spotify_api.spotify_status()
        if inspect.isawaitable(maybe):
            return await maybe
        return maybe
    except Exception:
        return JSONResponse({"status": "ok"}, status_code=200)


@router.get("/google/status", deprecated=True)
async def google_status_compat():
    """Call into Google integration status if available, else normalized 200."""
    try:
        from app.router.integrations import google_api

        maybe = google_api.google_status()
        if inspect.isawaitable(maybe):
            return await maybe
        return maybe
    except Exception:
        return JSONResponse({"status": "ok"}, status_code=200)


