from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request, HTTPException

from ..deps.user import get_current_user_id
from ..integrations.spotify.client import SpotifyClient, SpotifyAuthError

router = APIRouter(prefix="/v1/spotify", tags=["spotify"])
logger = logging.getLogger(__name__)


@router.get("/devices")
async def devices(request: Request, user_id: str = Depends(get_current_user_id)):
    client = SpotifyClient(user_id)
    try:
        devices = await client.get_devices()
    except SpotifyAuthError:
        raise HTTPException(status_code=401, detail="spotify_not_authenticated")
    except Exception as e:
        logger.exception("spotify.devices_error")
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
        context_uri = body.get("context_uri")
        success = await client.play(uris=uris, context_uri=context_uri)
        if not success:
            raise HTTPException(status_code=502, detail="play_failed")
    except SpotifyAuthError:
        raise HTTPException(status_code=401, detail="spotify_not_authenticated")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("spotify.play_error")
        raise HTTPException(status_code=502, detail="spotify_error")
    return {"ok": True}


