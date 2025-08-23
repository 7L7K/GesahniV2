from fastapi import APIRouter, Request, Response, Depends

router = APIRouter()

from .auth import dev_token, dev_login, make_dev_token  # lightweight dev helpers
from .deps.user import get_current_user_id


@router.post("/auth/dev/login")
async def dev_login_route(body: dict, request: Request, response: Response):
    return await dev_login(body, request, response)


@router.post("/auth/token")
async def dev_token_route(body: dict, user_id: str = Depends(get_current_user_id)):
    # Issue a dev token (only enabled in dev via environment guards in implementation)
    return await make_dev_token(body, user_id)
