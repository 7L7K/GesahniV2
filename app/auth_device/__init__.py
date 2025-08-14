"""Device trust/session rotation for Granny Mode.

Separate from `app/auth.py` to avoid conflicts. Provides a router for trusted
device sessions without interactive login on the TV.
"""

import os
import time
import jwt
from fastapi import APIRouter, Response

router = APIRouter(prefix="/device", tags=["Auth"])


@router.get("/session")
async def get_device_session() -> dict:
    # Placeholder: returns a synthetic long-lived session with rotation marker
    return {"status": "ok", "session": {"trusted": True, "rotate_after": 86400}}


@router.post("/trust")
async def trust_device(response: Response) -> dict:
    """Issue a device-trusted session.

    If JWT_SECRET is configured, set an access_token cookie with a long TTL.
    Otherwise, set a lightweight marker cookie so the UI can behave consistently
    in test/dev environments. The silent refresh middleware rotates as needed.
    """
    now = int(time.time())
    lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))  # default 14d
    cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    secret = os.getenv("JWT_SECRET")
    if secret:
        payload = {"user_id": "device", "iat": now, "exp": now + lifetime}
        token = jwt.encode(payload, secret, algorithm="HS256")
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=cookie_secure,
            samesite=cookie_samesite,
            max_age=lifetime,
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
        max_age=lifetime,
        path="/",
    )
    return {"status": "ok", "trusted": True, "cookie": "device_trust"}


