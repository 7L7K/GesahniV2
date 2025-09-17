from __future__ import annotations

import asyncio
import logging
import os
import random
import time

import jwt
from fastapi import APIRouter, HTTPException, Request, Response

from app.auth.cookie_utils import set_all_auth_cookies
from app.auth.errors import ERR_TOO_MANY
from app.auth.jwt_utils import _decode_any
from app.auth.models import LoginOut
from app.auth.rate_limit_utils import _get_refresh_ttl_seconds, _is_rate_limit_enabled
from app.auth_debug import log_set_cookie
from app.auth_protection import public_route
from app.auth_refresh import _get_or_create_device_id
from app.cookie_config import get_cookie_config, get_token_ttls
from app.deps.user import resolve_session_id
from app.models.user import get_user_async
from app.token_store import allow_refresh
from app.tokens import make_access, make_refresh
from app.user_store import user_store

router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
logger = logging.getLogger(__name__)


@router.post(
    "/login",
    response_model=LoginOut,
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {"example": {"status": "ok", "user_id": "dev"}}
                }
            }
        }
    },
)
@public_route
async def login(
    request: Request,
    response: Response,
):
    """Dev login scaffold.

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """

    # Extract username from multiple sources, but prioritize for backoff checking
    username = request.query_params.get("username")

    # Accept username from JSON, then form, then query param
    if not username:
        body_username: str | None = None
        form_username: str | None = None
        # JSON first
        try:
            body = await request.json()
            if isinstance(body, dict):
                v = body.get("username")
                if isinstance(v, str) and v.strip():
                    body_username = v.strip()
        except Exception:
            body_username = None
        # Form as fallback
        if not body_username:
            try:
                form = await request.form()
                v = form.get("username") if form else None
                if isinstance(v, str) and v.strip():
                    form_username = v.strip()
            except Exception:
                form_username = None
        username = body_username or form_username or username

    # Apply exponential backoff for rate limiting before authentication
    if username:
        user_key = f"user:{username}"
        try:
            # Read environment variables at runtime
            threshold = int(os.getenv("LOGIN_BACKOFF_THRESHOLD", "3"))
            start_ms = int(os.getenv("LOGIN_BACKOFF_START_MS", "200"))
            max_ms = int(os.getenv("LOGIN_BACKOFF_MAX_MS", "1000"))

            from app.auth import _attempts  # expected: dict[str, tuple[int, float]]

            if isinstance(_attempts, dict) and user_key in _attempts:
                count, _ = _attempts.get(user_key, (0, 0.0))
                if count >= threshold:
                    delay_ms = random.randint(start_ms, max_ms)
                    await asyncio.sleep(delay_ms / 1000.0)
        except Exception:
            pass

    # Smart minimal login: accept any non-empty username for dev; in prod plug real check
    if not username:
        from app.auth.errors import ERR_MISSING_USERNAME
        from app.http_errors import http_error

        raise http_error(
            code=ERR_MISSING_USERNAME, message="Username is required", status=400
        )
    # Rate-limit login attempts: IP 5/min & 30/hour; username 10/hour
    try:
        if _is_rate_limit_enabled():
            from app.token_store import (
                _key_login_ip,
                _key_login_user,
                incr_login_counter,
            )

            ip = request.client.host if request and request.client else "unknown"
            if await incr_login_counter(_key_login_ip(f"{ip}:m"), 60) > 5:
                raise HTTPException(status_code=429, detail=ERR_TOO_MANY)
            if await incr_login_counter(_key_login_ip(f"{ip}:h"), 3600) > 30:
                raise HTTPException(status_code=429, detail=ERR_TOO_MANY)
            if await incr_login_counter(_key_login_user(username), 3600) > 10:
                raise HTTPException(status_code=429, detail=ERR_TOO_MANY)
    except HTTPException:
        raise
    except Exception:
        pass

    # Use centralized cookie configuration for sharp and consistent cookies
    get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()

    # Get or create device_id for token binding
    device_id = _get_or_create_device_id(request, response)

    jwt_token = make_access(
        {"user_id": username, "device_id": device_id}, ttl_s=access_ttl
    )

    # Also issue a refresh token and mark it allowed for this session
    refresh_token = None
    session_id = None
    try:
        # Longer refresh in prod: default 7 days (604800s), allow override via env
        refresh_life = _get_refresh_ttl_seconds()
        import os as _os

        jti = jwt.api_jws.base64url_encode(_os.urandom(16)).decode()
        refresh_token = make_refresh(
            {"user_id": username, "jti": jti, "device_id": device_id},
            ttl_s=refresh_life,
        )

        # Create opaque session ID instead of using JWT
        try:
            from app.auth import _create_session_id

            payload = _decode_any(jwt_token)
            jti = payload.get("jti")
            expires_at = payload.get("exp", time.time() + access_ttl)
            if jti:
                session_id = _create_session_id(jti, expires_at)
            else:
                session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
        except Exception as e:
            logger.warning(f"Failed to create session ID: {e}")
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

        # Centralized cookie set + legacy + device cookie in one helper
        set_all_auth_cookies(
            response,
            request,
            access=jwt_token,
            refresh=refresh_token,
            session_id=session_id,
            access_ttl=access_ttl,
            refresh_ttl=refresh_ttl,
            append_legacy=True,
            ensure_device_cookie=True,
        )

        # Allow refresh for this session family
        sid = resolve_session_id(request=request, user_id=username)
        await allow_refresh(sid, jti, ttl_seconds=refresh_ttl)
    except Exception as e:
        # Best-effort; login still succeeds with access token alone
        logger.error(f"Exception in login cookie setting: {e}")
    # Get the user's UUID for user_store operations
    user = await get_user_async(username)
    if user:
        await user_store.ensure_user(user.id)
        await user_store.update_login_stats(user.id)
    # Debug: print Set-Cookie headers sent
    try:
        if os.getenv("AUTH_DEBUG") == "1":
            log_set_cookie(response, route="/v1/auth/login", user_id=username)
    except Exception:
        pass
    # Always return tokens in dev login to support header-auth mode and debugging.
    # In cookie mode the client may ignore these fields.
    return {
        "status": "ok",
        "user_id": username,
        "access_token": jwt_token,
        "refresh_token": refresh_token,
        "session_id": session_id,
    }


# Aliases for legacy compatibility
login_v1 = login
