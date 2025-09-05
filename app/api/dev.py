import os
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
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

    from ..tokens import SECRET_KEY, ALGORITHM
    from ..sessions_store import sessions_store
    from ..web.cookies import set_auth_cookies, set_csrf_cookie

    user_id = request.user_id
    ttl_minutes = request.ttl_minutes

    # Create JWT payload
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ttl_minutes)
    payload = {
        "user_id": user_id,
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    # Encode token
    try:
        from jose import jwt as jose_jwt
        access_token = jose_jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    except ImportError:
        raise HTTPException(status_code=500, detail="JWT library not available")

    # Create session
    session_id = await sessions_store.create_session(user_id)

    # Set cookies
    set_auth_cookies(response, access=access_token, session_id=session_id, access_ttl=ttl_minutes*60)

    return Response(status_code=204)
