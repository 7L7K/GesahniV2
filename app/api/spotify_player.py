from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth_core import require_scope
from ..deps.user import get_current_user_id
from ..integrations.spotify.client import (
    SpotifyAuthError,
    SpotifyClient,
    SpotifyRateLimitedError,
)
from ..metrics import (
    SPOTIFY_DEVICE_LIST_COUNT,
    SPOTIFY_DEVICES_REQUEST_COUNT,
    SPOTIFY_PLAY_COUNT,
)

# Import verify_token directly to avoid circular import issues

router = APIRouter(
    prefix="/v1/spotify",
    tags=["Music"],
    dependencies=[Depends(require_scope("music:control"))],
)
logger = logging.getLogger(__name__)


@router.get("/devices")
async def devices(request: Request, user_id: str = Depends(get_current_user_id)):
    logger.info(
        "🎵 SPOTIFY DEVICES: Request started",
        extra={
            "user_id": user_id,
            "route": "/v1/spotify/devices",
            "auth_state": (
                "spotify_linked=true" if user_id != "anon" else "spotify_linked=false"
            ),
        },
    )

    client = SpotifyClient(user_id)
    try:
        devices = await client.get_devices()
        try:
            SPOTIFY_DEVICE_LIST_COUNT.labels(status="ok").inc()
            SPOTIFY_DEVICES_REQUEST_COUNT.labels(
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
            "🎵 SPOTIFY DEVICES: Request successful",
            extra={
                "user_id": user_id,
                "route": "/v1/spotify/devices",
                "auth_state": (
                    "spotify_linked=true"
                    if user_id != "anon"
                    else "spotify_linked=false"
                ),
                "meta": {"device_count": len(devices) if devices else 0},
            },
        )
    except SpotifyRateLimitedError as e:
        # Surface upstream rate limit with Retry-After when available
        from fastapi.responses import Response

        logger.warning(
            "🎵 SPOTIFY DEVICES: Rate limited",
            extra={
                "user_id": user_id,
                "route": "/v1/spotify/devices",
                "auth_state": (
                    "spotify_linked=true"
                    if user_id != "anon"
                    else "spotify_linked=false"
                ),
                "meta": {
                    "retry_after": (
                        str(e.retry_after) if getattr(e, "retry_after", None) else None
                    )
                },
            },
        )

        retry_after = str(e.retry_after) if getattr(e, "retry_after", None) else None
        headers = {"Retry-After": retry_after} if retry_after else {}

        try:
            SPOTIFY_DEVICE_LIST_COUNT.labels(status="fail").inc()
            SPOTIFY_DEVICES_REQUEST_COUNT.labels(
                status="429",
                auth_state=(
                    "spotify_linked=true"
                    if user_id != "anon"
                    else "spotify_linked=false"
                ),
            ).inc()
        except Exception:
            pass

        return Response(status_code=429, headers=headers)
    except SpotifyAuthError:
        logger.warning(
            "🎵 SPOTIFY DEVICES: Auth error",
            extra={
                "user_id": user_id,
                "route": "/v1/spotify/devices",
                "auth_state": "spotify_linked=false",
            },
        )

        try:
            SPOTIFY_DEVICE_LIST_COUNT.labels(status="fail").inc()
            SPOTIFY_DEVICES_REQUEST_COUNT.labels(
                status="401", auth_state="spotify_linked=false"
            ).inc()
        except Exception:
            pass
        from ..http_errors import unauthorized

        raise unauthorized(
            code="spotify_not_authenticated",
            message="Spotify not authenticated",
            hint="connect Spotify account",
        )
    except Exception:
        logger.exception("spotify.devices_error")
        try:
            SPOTIFY_DEVICE_LIST_COUNT.labels(status="fail").inc()
            SPOTIFY_DEVICES_REQUEST_COUNT.labels(
                status="502",
                auth_state=(
                    "spotify_linked=true"
                    if user_id != "anon"
                    else "spotify_linked=false"
                ),
            ).inc()
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="spotify_error")
    return {"ok": True, "devices": devices}


@router.post("/play")
async def play(
    request: Request, body: dict, user_id: str = Depends(get_current_user_id)
):
    """Proxy play request to Spotify.

    Body shape: { "uris"?: [], "context_uri"?: "", "device_id"?: "" }
    """
    # Optional CSRF guard (enabled when CSRF_ENABLED=1)
    try:
        from app.auth_core import csrf_validate

        csrf_validate(request)
    except Exception:
        pass

    client = SpotifyClient(user_id)
    device_id = body.get("device_id")
    try:
        if device_id:
            # Transfer playback to requested device (best-effort)
            await client.transfer_playback(device_id, play=False)

        uris = body.get("uris")
        # Minimal support: client.play accepts optional URIs list
        success = await client.play(uris=uris)
        if not success:
            try:
                SPOTIFY_PLAY_COUNT.labels(status="fail").inc()
            except Exception:
                pass
            raise HTTPException(status_code=502, detail="play_failed")
    except SpotifyRateLimitedError as e:
        from fastapi.responses import Response

        retry_after = str(e.retry_after) if getattr(e, "retry_after", None) else None
        headers = {"Retry-After": retry_after} if retry_after else {}
        return Response(status_code=429, headers=headers)
    except SpotifyAuthError:
        try:
            SPOTIFY_PLAY_COUNT.labels(status="fail").inc()
        except Exception:
            pass
        from ..http_errors import unauthorized

        raise unauthorized(
            code="spotify_not_authenticated",
            message="Spotify not authenticated",
            hint="connect Spotify account",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("spotify.play_error")
        try:
            SPOTIFY_PLAY_COUNT.labels(status="fail").inc()
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="spotify_error")
    try:
        SPOTIFY_PLAY_COUNT.labels(status="ok").inc()
    except Exception:
        pass
    return {"ok": True}
