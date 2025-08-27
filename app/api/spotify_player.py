from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request, HTTPException

from ..deps.user import get_current_user_id
from ..integrations.spotify.client import SpotifyClient, SpotifyAuthError
from ..security import verify_token
from ..metrics import SPOTIFY_PLAY_COUNT, SPOTIFY_DEVICE_LIST_COUNT
import logging

router = APIRouter(prefix="/v1/spotify", tags=["spotify"], dependencies=[Depends(verify_token)])
logger = logging.getLogger(__name__)


@router.get("/devices")
async def devices(request: Request, user_id: str = Depends(get_current_user_id)):
    client = SpotifyClient(user_id)
    try:
        devices = await client.get_devices()
        try:
            SPOTIFY_DEVICE_LIST_COUNT.labels(status="ok").inc()
        except Exception:
            pass
    except SpotifyAuthError:
        try:
            SPOTIFY_DEVICE_LIST_COUNT.labels(status="fail").inc()
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="spotify_not_authenticated")
    except Exception as e:
        logger.exception("spotify.devices_error")
        try:
            SPOTIFY_DEVICE_LIST_COUNT.labels(status="fail").inc()
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="spotify_error")
    return {"ok": True, "devices": devices}


@router.post("/play")
async def play(request: Request, body: dict, user_id: str = Depends(get_current_user_id)):
    """Proxy play request to Spotify.

    Body shape: { "uris"?: [], "context_uri"?: "", "device_id"?: "" }
    """
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
    except SpotifyAuthError:
        try:
            SPOTIFY_PLAY_COUNT.labels(status="fail").inc()
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="spotify_not_authenticated")
    except HTTPException:
        raise
    except Exception as e:
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
