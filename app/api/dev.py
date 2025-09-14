import os

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

router = APIRouter(tags=["Dev"])


def _is_dev():
    return os.getenv("ENV", "dev").lower() in {"dev", "local"} or os.getenv(
        "DEV_MODE", "0"
    ).lower() in {"1", "true", "yes", "on"}


class MintAccessRequest(BaseModel):
    user_id: str
    ttl_minutes: int = 15


@router.post("/mint_access", include_in_schema=False)
async def mint_access(request: MintAccessRequest, response: Response):
    """Mint a short-lived access token for dev testing."""
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")

    from ..sessions_store import sessions_store
    from ..tokens import sign_access_token
    from ..web.cookies import set_auth_cookies

    user_id = request.user_id
    ttl_minutes = request.ttl_minutes

    # Create access token using centralized configuration
    access_token = sign_access_token(
        user_id,
        extra={"ttl_override": ttl_minutes},  # Custom TTL for dev testing
    )

    # Create session
    session_id = await sessions_store.create_session(user_id)

    # Set cookies
    set_auth_cookies(
        response,
        access=access_token,
        session_id=session_id,
        access_ttl=ttl_minutes * 60,
    )

    return Response(status_code=204)
