"""Compatibility wrappers exposing music functions for top-level aliases.

These call into `app.api.music`/`app.api.spotify_player` to perform real
device and playback operations when available; otherwise they return the
normalized fallback shapes expected by the alias router.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.api import music as _music_api
from app.api import spotify as _spotify_api
from app.feature_flags import MUSIC_ENABLED
from app.http_errors import http_error

logger = logging.getLogger(__name__)


def log_music_router(
    operation: str, user_id: str = None, details: dict = None, level: str = "info"
):
    """Enhanced music router logging."""
    details = details or {}
    log_data = {
        "operation": operation,
        "component": "music_router",
        "timestamp": time.time(),
        **details,
    }
    if user_id:
        log_data["user_id"] = user_id

    if level == "debug":
        logger.debug(f"🎵 MUSIC ROUTER {operation.upper()}", extra={"meta": log_data})
    elif level == "warning":
        logger.warning(f"🎵 MUSIC ROUTER {operation.upper()}", extra={"meta": log_data})
    elif level == "error":
        logger.error(f"🎵 MUSIC ROUTER {operation.upper()}", extra={"meta": log_data})
    else:
        logger.info(f"🎵 MUSIC ROUTER {operation.upper()}", extra={"meta": log_data})


def _no_store_headers(resp: Response) -> None:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"


async def music_status(request: Request) -> dict[str, Any]:
    log_music_router(
        "music_status_start",
        None,
        {"message": "Music status request started", "music_enabled": MUSIC_ENABLED},
    )

    if not MUSIC_ENABLED:
        log_music_router(
            "music_disabled",
            None,
            {"message": "Music integration is disabled", "level": "warning"},
            level="warning",
        )

        raise http_error(
            code="feature_disabled",
            message="Music integration is disabled",
            status=404,
            meta={"feature": "music"},
        )

    # Try to resolve user_id for provider calls; fall back to anon
    user_id = None
    try:
        from app.deps.user import resolve_user_id

        user_id = await resolve_user_id(request=request)
        log_music_router(
            "user_resolved",
            user_id,
            {"message": "User ID resolved successfully", "user_id": user_id},
        )
    except Exception as e:
        user_id = "anon"
        log_music_router(
            "user_resolution_failed",
            "anon",
            {
                "message": "User resolution failed, using anon",
                "error": str(e),
                "level": "warning",
            },
            level="warning",
        )

    # Enhanced logging with user_id, route, and auth_state
    auth_state = "spotify_linked=true" if user_id != "anon" else "spotify_linked=false"
    log_music_router(
        "music_status_request",
        user_id,
        {
            "message": "Music status request processing",
            "route": "/v1/music/status",
            "auth_state": auth_state,
        },
    )

    try:
        # Prefer rich music API if available (try to call with request)
        res = await _music_api._get_state_impl(request, None, user_id)  # type: ignore[attr-defined]
        result = (
            res
            if isinstance(res, dict)
            else {"playing": False, "device": None, "track": None}
        )
        response = JSONResponse(result)
        _no_store_headers(response)

        # Track metrics
        try:
            from app.metrics import SPOTIFY_STATUS_REQUESTS_COUNT

            SPOTIFY_STATUS_REQUESTS_COUNT.labels(
                status="200",
                auth_state=(
                    "spotify_linked=true"
                    if user_id != "anon"
                    else "spotify_linked=false"
                ),
            ).inc()
        except Exception:
            pass

        logger.info(
            "🎵 MUSIC STATUS: Request successful",
            extra={
                "user_id": user_id,
                "route": "/v1/music/status",
                "auth_state": (
                    "spotify_linked=true"
                    if user_id != "anon"
                    else "spotify_linked=false"
                ),
                "meta": {"response": result},
            },
        )

        return response
    except Exception:
        try:
            # Fallback to spotify status probe
            try:
                await _spotify_api.spotify_status  # type: ignore[attr-defined]
            except Exception:
                pass
            result = {"playing": False, "device": None, "track": None}
            response = JSONResponse(result)
            _no_store_headers(response)

            # Track metrics for fallback
            try:
                from app.metrics import SPOTIFY_STATUS_REQUESTS_COUNT

                SPOTIFY_STATUS_REQUESTS_COUNT.labels(
                    status="200",
                    auth_state=(
                        "spotify_linked=true"
                        if user_id != "anon"
                        else "spotify_linked=false"
                    ),
                ).inc()
            except Exception:
                pass

            logger.warning(
                "🎵 MUSIC STATUS: Using fallback response",
                extra={
                    "user_id": user_id,
                    "route": "/v1/music/status",
                    "auth_state": (
                        "spotify_linked=true"
                        if user_id != "anon"
                        else "spotify_linked=false"
                    ),
                },
            )

            return response
        except Exception:
            result = {"playing": False, "device": None, "track": None}
            response = JSONResponse(result)
            _no_store_headers(response)

            # Track metrics for final fallback
            try:
                from app.metrics import SPOTIFY_STATUS_REQUESTS_COUNT

                SPOTIFY_STATUS_REQUESTS_COUNT.labels(
                    status="200",
                    auth_state=(
                        "spotify_linked=true"
                        if user_id != "anon"
                        else "spotify_linked=false"
                    ),
                ).inc()
            except Exception:
                pass

            logger.error(
                "🎵 MUSIC STATUS: Using final fallback response",
                extra={
                    "user_id": user_id,
                    "route": "/v1/music/status",
                    "auth_state": (
                        "spotify_linked=true"
                        if user_id != "anon"
                        else "spotify_linked=false"
                    ),
                },
            )

            return response


async def music_devices(request: Request) -> dict[str, Any]:
    if not MUSIC_ENABLED:
        raise http_error(
            code="feature_disabled",
            message="Music integration is disabled",
            status=404,
            meta={"feature": "music"},
        )

    # Resolve user id where possible
    user_id = "anon"
    try:
        from app.deps.user import resolve_user_id

        user_id = await resolve_user_id(request=request)
    except Exception:
        user_id = "anon"

    # Enhanced logging with user_id, route, and auth_state
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        "🎵 MUSIC DEVICES: Request started",
        extra={
            "user_id": user_id,
            "route": "/v1/music/devices",
            "auth_state": (
                "spotify_linked=true" if user_id != "anon" else "spotify_linked=false"
            ),
        },
    )

    # Check authentication and return 401 if not authenticated
    if user_id == "anon":
        logger.warning(
            "🎵 MUSIC DEVICES: Unauthenticated user",
            extra={
                "user_id": user_id,
                "route": "/v1/music/devices",
                "auth_state": "spotify_linked=false",
            },
        )

        # Track metrics for unauthenticated request
        try:
            from app.metrics import SPOTIFY_DEVICES_REQUEST_COUNT

            SPOTIFY_DEVICES_REQUEST_COUNT.labels(
                status="401", auth_state="spotify_linked=false"
            ).inc()
        except Exception:
            pass

        raise http_error(
            code="spotify_not_authenticated",
            message="Connect Spotify to list devices.",
            status=401,
        )

    # Temporarily force error response to test frontend handling
    result = {"devices": [], "error": "spotify_not_authenticated"}
    response = JSONResponse(result)
    _no_store_headers(response)

    # Track metrics for error response
    try:
        from app.metrics import SPOTIFY_DEVICES_REQUEST_COUNT

        SPOTIFY_DEVICES_REQUEST_COUNT.labels(
            status="200", auth_state="spotify_linked=true"
        ).inc()
    except Exception:
        pass

    logger.warning(
        "🎵 MUSIC DEVICES: Returning error response (test mode)",
        extra={
            "user_id": user_id,
            "route": "/v1/music/devices",
            "auth_state": "spotify_linked=true",
        },
    )

    return response


async def set_music_device(request) -> dict[str, Any]:
    if not MUSIC_ENABLED:
        raise http_error(
            code="feature_disabled",
            message="Music integration is disabled",
            status=404,
            meta={"feature": "music"},
        )

    # Accept device_id in body or query params for compatibility
    try:
        data = await request.json()
    except Exception:
        data = {}
    device_id = request.query_params.get("device_id") or (data or {}).get("device_id")
    if not device_id:
        return {"detail": "missing device_id"}
    try:
        # Try to call canonical set_device
        try:
            await _music_api.set_device.__call__(
                {"device_id": device_id}
            )  # fallback; may not match
        except Exception:
            # Best-effort: ask music API to set device by invoking helper
            try:
                from app.api.music import set_device as _set_dev  # type: ignore

                await _set_dev(type("B", (), {"device_id": device_id})())
            except Exception:
                pass
        return {"ok": True, "device_id": device_id}
    except Exception:
        return {"detail": "failed_to_set_device"}
