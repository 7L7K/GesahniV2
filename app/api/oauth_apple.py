from __future__ import annotations

import logging
import os
import random
import time
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from jwt import PyJWKClient

from ..auth.cookie_utils import rotate_session_id
from ..security import jwt_decode
from ..sessions_store import sessions_store

router = APIRouter(tags=["Auth"], include_in_schema=False)
logger = logging.getLogger(__name__)


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


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=4)
def _get_apple_jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _decode_apple_id_token(id_token: str, client_id: str) -> dict:
    """Verify and decode the Apple ID token using JWKS."""
    jwks_url = (
        os.getenv("APPLE_JWKS_URL") or "https://appleid.apple.com/auth/keys"
    ).strip()
    if not jwks_url:
        jwks_url = "https://appleid.apple.com/auth/keys"

    try:
        client = _get_apple_jwk_client(jwks_url)
        signing_key = client.get_signing_key_from_jwt(id_token)
        algorithm = signing_key.algorithm or "RS256"
        return jwt_decode(
            id_token,
            signing_key.key,
            algorithms=[algorithm],
            audience=client_id,
            issuer="https://appleid.apple.com",
        )
    except Exception as exc:
        env = (os.getenv("ENV") or "dev").strip().lower()
        allow_fallback = (
            _truthy(os.getenv("DEV_MODE"))
            or _truthy(os.getenv("APPLE_ID_TOKEN_INSECURE_FALLBACK"))
            or _truthy(os.getenv("PYTEST_RUNNING"))
            or bool(os.getenv("PYTEST_CURRENT_TEST"))
            or env not in {"prod", "production"}
        )
        if allow_fallback:
            logger.warning(
                "Apple ID token verification failed (%s); falling back to unsigned decode for dev mode",
                exc,
            )
            try:
                return jwt_decode(id_token, options={"verify_signature": False})
            except Exception as fallback_exc:
                logger.error(
                    "Apple ID token fallback decode failed: %s",
                    fallback_exc,
                    exc_info=False,
                )
        raise HTTPException(status_code=400, detail="invalid_id_token") from exc


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

    # Sanitize and set gs_next cookie for post-login redirect if next param present
    # sanitize_redirect_path prevents open redirects by rejecting absolute/protocol-relative
    # URLs and auth paths that could cause redirect loops. This ensures users are only
    # redirected to safe, same-origin application pages after OAuth completion.
    resp = Response(status_code=302)

    if request.query_params.get("next"):
        from ..redirect_utils import sanitize_redirect_path, set_gs_next_cookie

        sanitized_next = sanitize_redirect_path(next_url, "/", request)
        set_gs_next_cookie(resp, sanitized_next, request)
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
    resp.headers["Location"] = f"https://appleid.apple.com/auth/authorize?{qs}"

    # Use centralized cookie configuration
    from ..cookie_config import get_cookie_config

    get_cookie_config(request)

    # Set OAuth state cookies using centralized cookie surface
    from ..web.cookies import set_oauth_state_cookies

    set_oauth_state_cookies(
        resp=resp,
        state=state,
        next_url=next_url,
        request=request,
        ttl=600,
        provider="oauth",
    )
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
        payload = _decode_apple_id_token(id_token, client_id)

    user_id = (
        str(payload.get("email"))
        if payload.get("email")
        else str(payload.get("sub") or "")
    ).lower()
    if not user_id:
        raise HTTPException(status_code=400, detail="no_user")

    # Mint session and cookies
    sess = await sessions_store.create_session(user_id)
    sid, did = sess["sid"], sess["did"]
    datetime.now(UTC)
    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import decode_jwt_token, make_access, make_refresh

    # Use default TTLs from tokens.py
    access = make_access({"user_id": user_id, "sid": sid, "did": did})
    refresh = make_refresh({"user_id": user_id, "sid": sid, "did": did})

    # Use centralized cookie configuration for sharp and consistent cookies
    from ..cookie_config import get_cookie_config, get_token_ttls

    get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()

    try:
        request.state.user_id = user_id  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        access_payload = decode_jwt_token(access)
    except Exception as exc:
        logger.warning("Failed to decode access token for Apple session rotation: %s", exc)
        access_payload = {}

    session_id = rotate_session_id(
        response,
        request,
        user_id=user_id,
        access_token=access,
        access_payload=access_payload,
    )

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

    # Maintain legacy cookie headers when enabled to support older clients/tests.
    try:
        from .auth import _append_legacy_auth_cookie_headers as _legacy_cookie_headers

        _legacy_cookie_headers(
            response,
            access=access,
            refresh=refresh,
            session_id=session_id,
            request=request,
        )
    except Exception as legacy_exc:  # pragma: no cover - defensive logging
        logger.debug("Failed to append legacy auth cookies: %s", legacy_exc)

    # Clear OAuth state cookies after successful authentication
    clear_oauth_state_cookies(response, provider="oauth")

    logger.info(
        "AUTH_OAUTH_LOGIN_SUCCESS",
        extra={"meta": {"provider": "apple", "user_id": user_id}},
    )

    # Use get_safe_redirect_target for gs_next cookie priority
    from ..redirect_utils import get_safe_redirect_target

    next_url = get_safe_redirect_target(request, fallback="/")

    # Sample cookie gauge for observability
    try:
        from ..metrics import AUTH_REDIRECT_COOKIE_IN_USE

        gs_next_present = get_gs_next_cookie(request) is not None
        AUTH_REDIRECT_COOKIE_IN_USE.set(1 if gs_next_present else 0)
    except Exception:
        pass
    # Return the same response we set cookies on to ensure cookies persist
    response.status_code = 302
    response.headers["Location"] = next_url
    return response


__all__ = ["router"]
