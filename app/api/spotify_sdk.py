from __future__ import annotations

from fastapi import APIRouter, Depends, Request, HTTPException

from ..deps.user import get_current_user_id
from ..integrations.spotify.client import SpotifyClient
from ..security import verify_token

router = APIRouter(prefix="/v1/spotify", tags=["spotify"], dependencies=[Depends(verify_token)])


@router.get("/token-for-sdk")
async def token_for_sdk(request: Request, user_id: str = Depends(get_current_user_id)):
    client = SpotifyClient(user_id)
    try:
        token = await client._bearer_token_only()
        return {"ok": True, "access_token": token}
    except RuntimeError as e:
        detail = str(e)
        if detail in ("not_connected", "needs_reauth"):
            raise HTTPException(status_code=401, detail=detail)
        raise

