from fastapi import APIRouter, Request, Response

router = APIRouter()

from ..auth_protection import auth_only_route
from .auth import refresh as _refresh_impl


@router.post("/auth/refresh")
@auth_only_route
async def refresh(request: Request, response: Response):
    """Refresh access token using valid refresh token.

    @auth_only_route - Auth token required, CSRF not required.
    """
    # Delegate to existing parity implementation in app.api.auth
    return await _refresh_impl(request, response)
