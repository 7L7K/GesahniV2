from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, HTTPException, Request, Response

from app.auth.cookie_utils import rotate_session_id, set_all_auth_cookies
from app.auth.errors import ERR_TOO_MANY
from app.auth.jwt_utils import _decode_any
from app.auth.models import LoginOut
from app.auth.rate_limit_utils import _get_refresh_ttl_seconds, _is_rate_limit_enabled
from app.auth_debug import log_set_cookie
from app.auth_protection import public_route
from app.auth_refresh import _get_or_create_device_id
from app.cookie_config import get_cookie_config, get_token_ttls
from app.deps.user import resolve_session_id
from app.models.user import get_user_async, create_user_async
from app.token_store import allow_refresh
from app.tokens import make_access, make_refresh
from app.user_store import user_store
from app.csrf import issue_csrf_token

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

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token header (header-token service).
    Rotates CSRF token on successful login.
    """

    # Extract client information for security logging
    client_ip = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
    user_agent = request.headers.get("User-Agent", "unknown")
    origin = request.headers.get("Origin", "unknown")

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
                logger.warning("🛡️ SECURITY_RATE_LIMIT_IP", extra={
                    "event_type": "rate_limit_exceeded",
                    "limit_type": "ip_per_minute",
                    "client_ip": ip,
                    "username": username,
                    "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
                    "origin": origin,
                    "timestamp": __import__('time').time(),
                })
                raise HTTPException(status_code=429, detail=ERR_TOO_MANY)
            if await incr_login_counter(_key_login_ip(f"{ip}:h"), 3600) > 30:
                logger.warning("🛡️ SECURITY_RATE_LIMIT_IP", extra={
                    "event_type": "rate_limit_exceeded",
                    "limit_type": "ip_per_hour",
                    "client_ip": ip,
                    "username": username,
                    "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
                    "origin": origin,
                    "timestamp": __import__('time').time(),
                })
                raise HTTPException(status_code=429, detail=ERR_TOO_MANY)
            if await incr_login_counter(_key_login_user(username), 3600) > 10:
                logger.warning("🛡️ SECURITY_RATE_LIMIT_USER", extra={
                    "event_type": "rate_limit_exceeded",
                    "limit_type": "user_per_hour",
                    "client_ip": ip,
                    "username": username,
                    "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
                    "origin": origin,
                    "timestamp": __import__('time').time(),
                })
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

    # Get or create user first to get the user's UUID
    logger.info(f"🔐 LOGIN_STEP_1: Looking up user '{username}'")
    user = await get_user_async(username)
    if not user:
        logger.info(f"🔐 LOGIN_STEP_2: User '{username}' not found, creating new user")
        # Create user if it doesn't exist (dev mode - no password required)
        import hashlib
        dummy_password = hashlib.sha256(f"{username}_dev_password".encode()).hexdigest()
        user = await create_user_async(username, dummy_password)
        logger.info(f"🔐 LOGIN_STEP_3: Created new user '{username}' with UUID: {user.id}")
    else:
        logger.info(f"🔐 LOGIN_STEP_2: Found existing user '{username}' with UUID: {user.id}")
    
    # Use the user's UUID for session creation
    logger.info(f"🔐 LOGIN_STEP_4: Creating session for user UUID: {user.id}")
    from app.sessions_store import sessions_store
    auth_session_result = await sessions_store.create_session(str(user.id), device_name="Web")
    auth_session_id = auth_session_result["sid"]
    logger.info(f"🔐 LOGIN_STEP_5: Created session with ID: {auth_session_id}")

    # Get the current session version
    sess_ver = await sessions_store.get_session_version(auth_session_id)
    logger.info(f"🔐 LOGIN_STEP_6: Got session version: {sess_ver}")

    logger.info(f"🔐 LOGIN_STEP_7: Creating JWT token with payload: user_id='{username}', alias='{username}', device_id='{device_id}', sid='{auth_session_id}', sess_ver={sess_ver}")
    jwt_token = make_access(
        {"user_id": username, "alias": username, "device_id": device_id, "sid": auth_session_id, "sess_ver": sess_ver}, ttl_s=access_ttl
    )
    logger.info(f"🔐 LOGIN_STEP_8: Created JWT access token (length: {len(jwt_token)})")

    # Also issue a refresh token and mark it allowed for this session
    refresh_token = None
    session_id = None
    try:
        # Longer refresh in prod: default 7 days (604800s), allow override via env
        refresh_life = _get_refresh_ttl_seconds()
        import os as _os

        jti = jwt.api_jws.base64url_encode(_os.urandom(16)).decode()
        logger.info(f"🔐 LOGIN_STEP_9: Creating refresh token with jti: {jti}")
        refresh_token = make_refresh(
            {"user_id": username, "jti": jti, "device_id": device_id, "sid": auth_session_id, "sess_ver": sess_ver},
            ttl_s=refresh_life,
        )
        logger.info(f"🔐 LOGIN_STEP_10: Created refresh token (length: {len(refresh_token)})")

        try:
            request.state.user_id = username  # type: ignore[attr-defined]
        except Exception:
            pass

        session_id = rotate_session_id(
            response,
            request,
            user_id=username,
            access_token=jwt_token,
            access_payload=_decode_any(jwt_token),
        )

        # Centralized cookie set + legacy + device cookie in one helper
        logger.info(f"🔐 LOGIN_STEP_11: Setting authentication cookies")
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
        logger.info(f"🔐 LOGIN_STEP_12: Authentication cookies set successfully")

        # Allow refresh for this session family
        sid = session_id or resolve_session_id(request=request, user_id=username)
        await allow_refresh(sid, jti, ttl_seconds=refresh_ttl)
    except Exception as e:
        # Best-effort; login still succeeds with access token alone
        logger.error(f"Exception in login cookie setting: {e}")
    
    # Update user store operations with the user we already have
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
    result = {
        "status": "ok",
        "user_id": username,
        "access_token": jwt_token,
        "refresh_token": refresh_token,
        "session_id": session_id,
        "is_authenticated": True,  # For frontend auth state synchronization
        "login_timestamp": datetime.now(UTC).isoformat(),
        "auth_source": "cookie",  # Indicates tokens set as cookies
        "session_ready": True,
        "_debug_backend_enhanced": True,  # Confirm enhanced backend is running
    }

    # Rotate CSRF token on successful login
    try:
        csrf_token = issue_csrf_token(response, request)
        result["csrf_token"] = csrf_token
        result["csrf"] = csrf_token
    except Exception:  # pragma: no cover - best effort
        pass

    # Prevent caches and intermediaries from reusing auth responses
    response.headers["Cache-Control"] = "no-store"
    try:
        del response.headers["ETag"]
    except KeyError:
        pass
    response.status_code = 200

    logger.info(f"🔐 LOGIN_SUCCESS: Login completed for user '{username}' - returning response with access_token and session_id")

    # Security event logging for successful authentication
    logger.info("🔐 SECURITY_AUTH_SUCCESS", extra={
        "event_type": "login_success",
        "username": username,
        "client_ip": client_ip,
        "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
        "origin": origin,
        "session_id": session_id,
        "timestamp": __import__('time').time(),
    })

    return result


# Aliases for legacy compatibility
login_v1 = login
