"""Device trust/session rotation for Granny Mode.

Separate from `app/auth.py` to avoid conflicts. Provides a router for trusted
device sessions without interactive login on the TV.
"""

import os
import time

import jwt
from fastapi import APIRouter, Request, Response

from ..security import jwt_decode

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
        # Use tokens.py facade instead of direct JWT encoding
        from ..tokens import make_access

        token = make_access({"user_id": "device"}, ttl_s=access_ttl)

        # Generate an opaque session ID for device trust
        from ..session_store import get_session_store

        store = get_session_store()
        # Extract JTI from the token for session mapping
        try:
            payload = jwt_decode(token, secret, algorithms=["HS256"])
            jti = payload.get("jti")
            expires_at = payload.get("exp")
            if jti and expires_at:
                session_id = store.create_session(jti, expires_at)
            else:
                # Fallback: generate a session ID without JTI mapping
                session_id = f"device_{int(time.time())}_{os.getpid()}"
        except Exception:
            # Fallback: generate a session ID without JTI mapping
            session_id = f"device_{int(time.time())}_{os.getpid()}"

        # Use centralized cookie functions
        from ..web.cookies import set_auth_cookies

        # For device trust, we set both access token and session cookie
        set_auth_cookies(
            response,
            access=token,
            refresh="",
            session_id=session_id,
            access_ttl=access_ttl,
            refresh_ttl=0,
            request=request,
        )
        return {"status": "ok", "trusted": True, "cookie": "access_token"}
    # Fallback marker cookie for environments without JWT configured
    # Harden: in production, refuse to set non-HttpOnly/non-Secure device_trust
    env = os.getenv("ENV", "dev").strip().lower()
    if env in {"prod", "production"}:
        try:
            logger.warning("device_trust.cookie_refused prod=true")
        except Exception:
            pass
        return {"status": "ok", "trusted": False, "cookie": None}  # type: ignore[return-value]
    # Use centralized cookie functions for device trust
    from ..cookies import set_device_cookie

    set_device_cookie(
        resp=response,
        value="1",
        ttl=access_ttl,
        request=request,
        cookie_name="device_trust",
    )
    return {"status": "ok", "trusted": True, "cookie": "device_trust"}
