from fastapi import APIRouter, Request

from .spotify import spotify_status as _spotify_status

router = APIRouter()


@router.get("/integrations/status")
async def integrations_status(request: Request):
    sp = await _spotify_status(request)
    # TODO: fill google, ha when ready
    return {"spotify": sp, "google": {"connected": False}, "home_assistant": {"connected": False}}


