import time

from fastapi import APIRouter, Request

from ..auth_store_tokens import get_token
from ..deps.user import resolve_user_id
from ..integrations.spotify.client import SpotifyClient

router = APIRouter()


@router.get("/integrations/status")
async def integrations_status(request: Request):
    spotify_result = {"connected": False}
    try:
        # Use resolve_user_id for internal calls to avoid raising in non-FastAPI contexts
        current_user = resolve_user_id(request=request)
        if current_user and current_user != "anon":
            client = SpotifyClient(current_user)
            try:
                # Actually test the Spotify API connection instead of just checking token existence
                profile = await client.get_user_profile()
                if profile is not None:
                    spotify_result = {"connected": True}
                else:
                    spotify_result = {
                        "connected": False,
                        "reason": "profile_check_failed",
                    }
            except RuntimeError as e:
                spotify_result = {"connected": False, "reason": str(e)}
    except Exception as e:
        spotify_result = {"connected": False, "reason": str(e)}

    # Compute Google provider health by inspecting tokens
    google_result = {"status": "not_connected"}
    try:
        current_user = resolve_user_id(request=request)
        if current_user and current_user != "anon":
            t = await get_token(current_user, "google")
            if not t:
                google_result = {"status": "not_connected"}
            else:
                # Simple truth: if is_valid false -> not_connected
                if not t.is_valid:
                    google_result = {"status": "not_connected", "reason": "invalid"}
                else:
                    # Degraded if expired and refresh would fail (we attempt probe)
                    now = int(time.time())
                    if (t.expires_at - now) < 300:
                        google_result = {
                            "status": "degraded",
                            "reason": "refresh_failed",
                        }
                    else:
                        google_result = {"status": "connected"}
    except Exception as e:
        google_result = {"status": "not_connected", "reason": str(e)}

    return {
        "spotify": spotify_result,
        "google": google_result,
        "home_assistant": {"connected": False},
    }
