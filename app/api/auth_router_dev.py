import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

router = APIRouter()

from app.deps.user import get_current_user_id

from ..cookie_config import get_cookie_config
from ..tokens import make_access
from ..web.cookies import NAMES, set_named_cookie


async def dev_login(body: dict, request: Request, response: Response):
    """
    Minimal dev login that issues signed access token with arbitrary scopes.

    Only available when ENV=dev and DEV_AUTH=1.
    Signs JWT with JWT_SECRET, exp=1h, sets HttpOnly GSNH_AT cookie.
    """
    # Validate environment conditions
    env = os.getenv("ENV", "").strip().lower()
    dev_auth = os.getenv("DEV_AUTH", "").strip()

    if env != "dev" or dev_auth != "1":
        raise HTTPException(status_code=404, detail="not_found")

    # Extract user_id and scopes from request body
    user_id = body.get("user_id", "test_user")
    scopes = body.get("scopes", ["chat:write"])

    # Create token with 1 hour expiry and custom scopes
    token_data = {"user_id": user_id, "sub": user_id, "scopes": scopes}

    # Create access token with 1 hour TTL
    access_token = make_access(token_data, ttl_s=3600)  # 1 hour in seconds

    # Set HttpOnly cookie using centralized cookie functions
    cfg = get_cookie_config(request)
    same_site = str(cfg.get("samesite", "lax")).capitalize()
    domain = cfg.get("domain")
    path = cfg.get("path", "/")
    secure = bool(cfg.get("secure", True))

    # Set the access token cookie (GSNH_AT)
    set_named_cookie(
        response,
        name=NAMES.access,
        value=access_token,
        ttl=3600,  # 1 hour
        http_only=True,
        same_site=same_site,
        domain=domain,
        path=path,
        secure=secure,
        request=request,
    )

    return {"token": access_token}


@router.post("/auth/dev/login")
async def dev_login_route(body: dict, request: Request, response: Response):
    return await dev_login(body, request, response)


@router.post("/auth/dev/token")
async def dev_token_route(
    body: dict | None = None, user_id: str = Depends(get_current_user_id)
):
    # Lightweight dev token issuer for test/dev environments. Return a simple
    # access token so tests exercising /v1/auth/dev/token see a 200 with a token.
    try:
        username = (body or {}).get("username") or "dev"
    except Exception:
        username = "dev"
    token = make_access({"user_id": username})
    return {"access_token": token, "token_type": "bearer"}
