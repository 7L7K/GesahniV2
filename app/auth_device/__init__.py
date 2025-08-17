"""Device trust/session rotation for Granny Mode.

Separate from `app/auth.py` to avoid conflicts. Provides a router for trusted
device sessions without interactive login on the TV.
"""

import os
import time
import jwt
from fastapi import APIRouter, Response, Request

router = APIRouter(prefix="/device", tags=["Auth"])


@router.get("/session")
async def get_device_session() -> dict:
    # Placeholder: returns a synthetic long-lived session with rotation marker
    return {"status": "ok", "session": {"trusted": True, "rotate_after": 86400}}


@router.post("/trust")
async def trust_device(request: Request, response: Response) -> dict:
    """Issue a device-trusted session.

    If JWT_SECRET is configured, set an access_token cookie with a long TTL.
    Otherwise, set a lightweight marker cookie so the UI can behave consistently
    in test/dev environments. The silent refresh middleware rotates as needed.
    """
    from ..cookie_config import get_cookie_config, get_token_ttls
    
    now = int(time.time())
    access_ttl, _ = get_token_ttls()
    cookie_config = get_cookie_config(request)
    secret = os.getenv("JWT_SECRET")
    if secret:
        payload = {"user_id": "device", "iat": now, "exp": now + access_ttl}
        token = jwt.encode(payload, secret, algorithm="HS256")
        try:
            from ..api.auth import _append_cookie_with_priority as _append
            _append(response, key="access_token", value=token, max_age=access_ttl, secure=cookie_config["secure"], samesite=cookie_config["samesite"])
        except Exception:
            response.set_cookie(
                key="access_token",
                value=token,
                httponly=True,
                secure=cookie_config["secure"],
                samesite=cookie_config["samesite"],
                max_age=access_ttl,
                path="/",
            )
        return {"status": "ok", "trusted": True, "cookie": "access_token"}
    # Fallback marker cookie for environments without JWT configured
    # Harden: in production, refuse to set non-HttpOnly/non-Secure device_trust
    env = (os.getenv("ENV", "dev").strip().lower())
    if env in {"prod", "production"}:
        try:
            print("device_trust.cookie_refused prod=true")
        except Exception:
            pass
        return {"status": "ok", "trusted": False, "cookie": None}  # type: ignore[return-value]
    response.set_cookie(
        key="device_trust",
        value="1",
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=access_ttl,
        path="/",
    )
    return {"status": "ok", "trusted": True, "cookie": "device_trust"}


