from fastapi import APIRouter, Depends, Request, Response

router = APIRouter()

from .auth import refresh as _refresh_impl


@router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    # Delegate to existing parity implementation in app.api.auth
    return await _refresh_impl(request, response)
