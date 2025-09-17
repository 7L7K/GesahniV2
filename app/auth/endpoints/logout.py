from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response

from app.auth_protection import auth_only_route
from app.deps.user import get_current_user_id

router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
logger = logging.getLogger(__name__)


@router.post(
    "/logout",
    responses={204: {"description": "Logout successful"}},
)
@auth_only_route
async def logout(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    """Logout user and clear all session data."""
    from app.auth.service import AuthService

    await AuthService.logout_user(request, response, user_id)

    response.status_code = 204
    return response


@router.post(
    "/logout_all",
    responses={204: {"description": "Logout all sessions for this family"}},
)
@auth_only_route
async def logout_all(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    """Logout from all sessions in this family."""
    from app.auth.service import AuthService

    await AuthService.logout_all_sessions(request, response, user_id)

    response.status_code = 204
    return response
