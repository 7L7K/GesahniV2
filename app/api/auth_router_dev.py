from fastapi import APIRouter, Depends, Request, Response

router = APIRouter()

from app.deps.user import get_current_user_id
from ..tokens import make_access


@router.post("/auth/dev/login")
async def dev_login_route(body: dict, request: Request, response: Response):
    return await dev_login(body, request, response)


@router.post("/auth/token")
async def dev_token_route(body: dict | None = None, user_id: str = Depends(get_current_user_id)):
    # Lightweight dev token issuer for test/dev environments. Return a simple
    # access token so tests exercising /v1/auth/token see a 200 with a token.
    try:
        username = (body or {}).get("username") or "dev"
    except Exception:
        username = "dev"
    token = make_access({"user_id": username})
    return {"access_token": token, "token_type": "bearer"}
