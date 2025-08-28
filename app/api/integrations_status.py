from fastapi import APIRouter, Request

from ..deps.user import get_current_user_id
from ..integrations.spotify.client import SpotifyClient

router = APIRouter()


@router.get("/integrations/status")
async def integrations_status(request: Request):
    """Get status of all integrations for the current user."""
    # Check Spotify status
    spotify_result = {"connected": False}
    
    try:
        # Get current user
        current_user = get_current_user_id(request=request)
        if current_user and current_user != "anon":
            # Check if user has valid Spotify tokens
            client = SpotifyClient(current_user)
            try:
                # Attempt to obtain a bearer token without making an API call
                token = await client._bearer_token_only()
                spotify_result = {"connected": True}
            except RuntimeError as e:
                spotify_result = {"connected": False, "reason": str(e)}
        else:
            spotify_result = {"connected": False, "reason": "not_authenticated"}
    except Exception as e:
        spotify_result = {"connected": False, "reason": f"error: {str(e)}"}
    
    # TODO: fill google, ha when ready
    return {
        "spotify": spotify_result, 
        "google": {"connected": False}, 
        "home_assistant": {"connected": False}
    }


