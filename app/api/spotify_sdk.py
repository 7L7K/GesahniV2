from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth_core import require_scope
from ..deps.user import get_current_user_id
from ..integrations.spotify.client import SpotifyClient
from ..security import verify_token

router = APIRouter(
    prefix="/v1/spotify",
    tags=["Music"],
    dependencies=[Depends(verify_token), Depends(require_scope("music:control"))],
)


@router.get("/token-for-sdk")
async def token_for_sdk(request: Request, user_id: str = Depends(get_current_user_id)):
    client = SpotifyClient(user_id)
    try:
        token = await client._bearer_token_only()
        return {"ok": True, "access_token": token}
    except RuntimeError as e:
        detail = str(e)
        if detail in ("not_connected", "needs_reauth"):
            from ..http_errors import unauthorized

            msg = (
                "spotify not connected"
                if detail == "not_connected"
                else "spotify needs reauth"
            )
            hint = (
                "connect Spotify account"
                if detail == "not_connected"
                else "reauthorize Spotify access"
            )
            raise unauthorized(code=detail, message=msg, hint=hint)
        raise
