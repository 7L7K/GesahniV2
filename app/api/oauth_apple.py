from __future__ import annotations

import os
import random
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..security import jwt_decode
from ..sessions_store import sessions_store

router = APIRouter(tags=["Auth"], include_in_schema=False)


def _allow_redirect(url: str) -> bool:
    allowed = os.getenv("OAUTH_REDIRECT_ALLOWLIST", "").split(",")
    allowed = [u.strip() for u in allowed if u.strip()]
    if not allowed:
        return True
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return any(host.endswith(a.lower()) for a in allowed)
    except Exception:
        return False


def _sign_client_secret(
    team_id: str, client_id: str, key_id: str, private_key_pem: str
) -> str:
    import jwt

    now = int(time.time())
    payload: dict[str, object] = {
        "iss": team_id,
        "iat": now,
        "exp": now + 60 * 10,
        "aud": "https://appleid.apple.com",
        "sub": client_id,
    }
    headers = {"kid": key_id}
    token = jwt.encode(payload, private_key_pem, algorithm="ES256", headers=headers)
    return token


@router.get("/auth/apple/start")
async def apple_start(request: Request) -> Response:
    client_id = os.getenv("APPLE_CLIENT_ID")
    redirect_uri = os.getenv("APPLE_REDIRECT_URI")
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="apple_oauth_unconfigured")
    next_url = request.query_params.get("next") or "/"
    if not _allow_redirect(next_url):
        next_url = "/"
    # Generate a random state and set short-lived cookies to validate callback and redirect target
    import secrets

    state = secrets.token_urlsafe(16)
    qs = urlencode(
        {
            "response_type": "code",
            "response_mode": "form_post",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "name email",
            "state": state,
        }
    )
    resp = Response(status_code=302)
    resp.headers["Location"] = f"https://appleid.apple.com/auth/authorize?{qs}"

    # Use centralized cookie configuration
    from ..cookie_config import get_cookie_config

    cookie_config = get_cookie_config(request)

    # Set OAuth state cookies using centralized cookie surface
    from ..web.cookies import set_oauth_state_cookies

    set_oauth_state_cookies(resp=resp, state=state, next_url=next_url, request=request, ttl=600, provider="oauth")
    return resp


@router.post("/auth/apple/callback")
async def apple_callback(request: Request, response: Response) -> Response:
    form = await request.form()
    code = form.get("code")
    state = form.get("state")
    if not code:
        raise HTTPException(status_code=400, detail="missing_code")
    # Validate state against double-submit cookie
    try:
        if (state or "") != (request.cookies.get("oauth_state") or ""):
            raise HTTPException(status_code=400, detail="bad_state")
    except HTTPException:
        raise
    except Exception:
        pass

    client_id = os.getenv("APPLE_CLIENT_ID")
    team_id = os.getenv("APPLE_TEAM_ID")
    key_id = os.getenv("APPLE_KEY_ID")
    private_key = os.getenv("APPLE_PRIVATE_KEY")
    redirect_uri = os.getenv("APPLE_REDIRECT_URI")
    if not all([client_id, team_id, key_id, private_key, redirect_uri]):
        raise HTTPException(status_code=500, detail="apple_oauth_unconfigured")

    client_secret = _sign_client_secret(team_id, client_id, key_id, private_key)
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=10) as s:
        r = await s.post("https://appleid.apple.com/auth/token", data=data)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail="token_exchange_failed")
        tok = r.json()
        id_token = tok.get("id_token")
        if not id_token:
            raise HTTPException(status_code=400, detail="no_id_token")
        # Basic decode without verification to extract email/sub

        try:
            payload = jwt_decode(id_token, options={"verify_signature": False})
        except Exception:
            payload = {}

    user_id = (
        str(payload.get("email"))
        if payload.get("email")
        else str(payload.get("sub") or "")
    ).lower()
    if not user_id:
        raise HTTPException(status_code=400, detail="no_user")

    # Mint session and cookies
    from ..auth import ALGORITHM, SECRET_KEY

    sess = await sessions_store.create_session(user_id)
    sid, did = sess["sid"], sess["did"]
    now = datetime.now(timezone.utc)
    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import make_access, make_refresh

    # Use default TTLs from tokens.py
    access = make_access({"user_id": user_id, "sid": sid, "did": did})
    refresh = make_refresh({"user_id": user_id, "sid": sid, "did": did})

    # Use centralized cookie configuration for sharp and consistent cookies
    from ..cookie_config import get_cookie_config, get_token_ttls

    cookie_config = get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()

    # Create opaque session ID instead of using JWT
    try:
        from ..auth import _create_session_id

        payload = jwt_decode(access, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        expires_at = payload.get("exp", time.time() + access_ttl)
        if jti:
            session_id = _create_session_id(jti, expires_at)
        else:
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to create session ID: {e}")
        session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

    # Use centralized cookie functions
    from ..web.cookies import clear_oauth_state_cookies, set_auth_cookies

    set_auth_cookies(
        response,
        access=access,
        refresh=refresh,
        session_id=session_id,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=request,
    )

    # Clear OAuth state cookies after successful authentication
    clear_oauth_state_cookies(response, request, provider="oauth")

    try:
        import logging

        logging.getLogger(__name__).info(
            "AUTH_OAUTH_LOGIN_SUCCESS",
            extra={"meta": {"provider": "apple", "user_id": user_id}},
        )
    except Exception:
        pass

    next_url = str(request.cookies.get("oauth_next") or "/")
    if not _allow_redirect(next_url):
        next_url = "/"
    # Return the same response we set cookies on to ensure cookies persist
    response.status_code = 302
    response.headers["Location"] = next_url
    return response


__all__ = ["router"]
