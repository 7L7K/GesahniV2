from __future__ import annotations

import base64
import os
import time
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..sessions_store import sessions_store


router = APIRouter(tags=["auth"], include_in_schema=False)


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


@router.get("/auth/google/start")
async def google_start(request: Request) -> Response:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="google_oauth_unconfigured")

    next_url = request.query_params.get("next") or "/"
    if not _allow_redirect(next_url):
        next_url = "/"

    # Create minimal PKCE values (optional)
    ver = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=")
    code_verifier = ver.decode()
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    state = base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip("=")
    # Persist verifier/state to short-lived cookie for callback
    resp = Response(status_code=302)
    resp.headers["Location"] = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
            }
        )
    )
    # TTL 10 minutes; enforce explicit SameSite and Secure where appropriate
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    same = cookie_samesite if cookie_samesite in {"lax", "strict", "none"} else "lax"
    try:
        secure = getattr(request.url, "scheme", "http") == "https"
    except Exception:
        secure = False
    resp.set_cookie("pkce_verifier", code_verifier, max_age=600, httponly=True, path="/", samesite=same, secure=secure)
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, path="/", samesite=same, secure=secure)
    resp.set_cookie("oauth_next", next_url, max_age=600, httponly=False, path="/", samesite=same, secure=secure)
    return resp


@router.get("/auth/google/callback")
async def google_callback(request: Request, response: Response) -> Response:
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing_code")
    if state != (request.cookies.get("oauth_state") or ""):
        raise HTTPException(status_code=400, detail="bad_state")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=500, detail="google_oauth_unconfigured")

    code_verifier = request.cookies.get("pkce_verifier") or ""
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=10) as s:
        r = await s.post("https://oauth2.googleapis.com/token", data=data)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail="token_exchange_failed")
        tok = r.json()
        id_token = tok.get("id_token")
        if not id_token:
            raise HTTPException(status_code=400, detail="no_id_token")
        r2 = await s.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {tok.get('access_token')}"})
        if r2.status_code != 200:
            raise HTTPException(status_code=400, detail="userinfo_failed")
        uinfo = r2.json()

    # Map user
    user_id = (uinfo.get("email") or uinfo.get("sub") or "").lower()
    if not user_id:
        raise HTTPException(status_code=400, detail="no_user")

    # Issue a session and cookies
    from ..auth import ALGORITHM, SECRET_KEY, EXPIRE_MINUTES, REFRESH_EXPIRE_MINUTES  # reuse settings
    import jwt
    from datetime import datetime, timedelta

    sess = await sessions_store.create_session(user_id)
    sid, did = sess["sid"], sess["did"]
    now = datetime.utcnow()
    access_payload = {"sub": user_id, "user_id": user_id, "sid": sid, "did": did, "type": "access", "exp": now + timedelta(minutes=EXPIRE_MINUTES)}
    refresh_payload = {"sub": user_id, "user_id": user_id, "sid": sid, "did": did, "type": "refresh", "exp": now + timedelta(minutes=REFRESH_EXPIRE_MINUTES)}
    access = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)
    refresh = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    # Use centralized cookie configuration for sharp and consistent cookies
    from ..cookie_config import get_cookie_config, get_token_ttls
    
    cookie_config = get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()
    
    try:
        from .auth import _append_cookie_with_priority as _append
        _append(response, key="access_token", value=access, max_age=access_ttl, secure=cookie_config["secure"], samesite=cookie_config["samesite"])
        _append(response, key="refresh_token", value=refresh, max_age=refresh_ttl, secure=cookie_config["secure"], samesite=cookie_config["samesite"])
    except Exception:
        response.set_cookie("access_token", access, httponly=True, secure=cookie_config["secure"], samesite=cookie_config["samesite"], max_age=access_ttl, path="/")
        response.set_cookie("refresh_token", refresh, httponly=True, secure=cookie_config["secure"], samesite=cookie_config["samesite"], max_age=refresh_ttl, path="/")

    # Audit
    try:
        import logging

        logging.getLogger(__name__).info("AUTH_OAUTH_LOGIN_SUCCESS", extra={"meta": {"provider": "google", "user_id": user_id}})
    except Exception:
        pass

    next_url = request.cookies.get("oauth_next") or "/"
    if not _allow_redirect(next_url):
        next_url = "/"
    # Clean redirect (no tokens in URL); cookies already set on 'response'
    response.status_code = 302
    response.headers["Location"] = next_url
    return response


__all__ = ["router"]


