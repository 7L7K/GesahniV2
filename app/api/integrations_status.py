from fastapi import APIRouter, Request

from ..deps.user import get_current_user_id
from ..integrations.spotify.client import SpotifyClient

router = APIRouter()


@router.get("/integrations/status")
async def integrations_status(request: Request):
    spotify_result = {"connected": False}
    try:
        current_user = get_current_user_id(request=request)
        if current_user and current_user != "anon":
            client = SpotifyClient(current_user)
            try:
                await client._bearer_token_only()
                spotify_result = {"connected": True}
            except RuntimeError as e:
                spotify_result = {"connected": False, "reason": str(e)}
    except Exception as e:
        spotify_result = {"connected": False, "reason": str(e)}

    return {
        "spotify": spotify_result,
        "google": {"connected": False},
        "home_assistant": {"connected": False},
    }


