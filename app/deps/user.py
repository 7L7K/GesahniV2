from __future__ import annotations

import logging
import os
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request, WebSocket

from ..security import _jwt_decode
from ..telemetry import LogRecord, hash_user_id, log_record_var

JWT_SECRET: str | None = None  # overridden in tests; env used when None

logger = logging.getLogger(__name__)


def _is_clerk_enabled() -> bool:
    """Check if Clerk authentication is enabled via environment variables."""
    return bool(
        os.getenv("CLERK_JWKS_URL")
        or os.getenv("CLERK_ISSUER")
        or os.getenv("CLERK_DOMAIN")
    )


def get_current_user_id(
    request: Request = None,
    websocket: WebSocket = None,
) -> str:
    """Return the current user's identifier.

    Token reading order:
    1. access_token (Authorization header, query param, or cookie)
    2. __session cookie (fallback) - contains opaque session ID only
    3. Never try to validate __session as a Clerk token unless Clerk is enabled
    4. Use the same JWT secret/issuer checks for both
    5. Log which cookie authenticated the request

    The resolved ID is attached to request/websocket state when authenticated.
    """
    if request and request.method == "OPTIONS":
        return "anon"

    target = request or websocket

    # 1) Grab or initialize our log record
    rec = log_record_var.get()
    if rec is None:
        rec = LogRecord(req_id=uuid4().hex)
        log_record_var.set(rec)

    user_id = ""
    token = None
    token_source = "none"

    # 2) Try access_token first (Authorization bearer, WS query param, or cookie)
    auth_header = None
    if target:
        auth_header = target.headers.get("Authorization")

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        token_source = "authorization_header"

    # WS query param fallback for browser WebSocket handshakes
    if token is None and websocket is not None:
        try:
            qp = websocket.query_params
            token = qp.get("access_token") or qp.get("token")
            if token:
                token_source = "websocket_query_param"
        except Exception:
            token = None

    # Cookie fallback so browser sessions persist without sending headers
    if token is None and request is not None:
        try:
            # Use canonical cookie name only
            from ..cookie_names import GSNH_AT

            token = request.cookies.get(GSNH_AT)
            if token:
                token_source = "access_token_cookie"
        except Exception:
            token = request.cookies.get("access_token")

    # Cookie header fallback for WS handshakes
    if token is None and websocket is not None:
        try:
            raw_cookie = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("access_token="):
                    token = p.split("=", 1)[1]
                    token_source = "websocket_access_token_cookie"
                    break
        except Exception:
            token = None

    # 3) Try __session cookie if access_token failed (contains opaque session ID only)
    if not token and request is not None:
        # Only treat __session as session cookie when Clerk is enabled; otherwise prefer canonical GSNH_SESS
        try:
            if os.getenv("CLERK_ENABLED", "0") == "1":
                session_token = request.cookies.get("__session") or request.cookies.get(
                    "session"
                )
            else:
                from ..cookie_names import GSNH_SESS

                session_token = request.cookies.get(GSNH_SESS)
        except Exception:
            session_token = request.cookies.get("session")
        if session_token:
            token = session_token
            token_source = "__session_cookie"

    # 4) Try __session cookie for WebSocket handshakes
    if not token and websocket is not None:
        try:
            raw_cookie = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("__session="):
                    token = p.split("=", 1)[1]
                    token_source = "websocket_session_cookie"
                    break
        except Exception:
            token = None

    # Enhanced logging for debugging auth issues
    try:
        logged_flag = None
        if target is not None:
            logged_flag = getattr(target.state, "auth_token_source_logged", None)
        if not logged_flag:
            request_path = (
                getattr(request, "url", {}).path
                if hasattr(getattr(request, "url", {}), "path")
                else "unknown" if request else "websocket"
            )
            
            if token:
                logger.info(
                    "auth.token_found",
                    extra={
                        "token_source": token_source,
                        "has_token": bool(token),
                        "token_length": len(token) if token else 0,
                        "token_preview": token[:20] + "..." if token and len(token) > 20 else token,
                        "request_path": request_path,
                        "all_cookies": list(request.cookies.keys()) if request else [],
                        "cookie_count": len(request.cookies) if request else 0,
                        "auth_header": bool(request.headers.get("Authorization")) if request else False,
                        "origin": request.headers.get("origin") if request else None,
                        "user_agent": request.headers.get("user-agent", "")[:50] if request else None
                    },
                )
            else:
                logger.info(
                    "auth.no_token",
                    extra={
                        "request_path": request_path,
                        "all_cookies": list(request.cookies.keys()) if request else [],
                        "cookie_count": len(request.cookies) if request else 0,
                        "auth_header": bool(request.headers.get("Authorization")) if request else False,
                        "origin": request.headers.get("origin") if request else None,
                        "user_agent": request.headers.get("user-agent", "")[:50] if request else None
                    },
                )
            # mark as logged for this request to avoid duplicate logs
            if target is not None:
                try:
                    setattr(target.state, "auth_token_source_logged", True)
                except Exception:
                    pass
    except Exception:
        # Best-effort logging only; don't let telemetry logging break auth flow
        pass

    secret = JWT_SECRET or os.getenv("JWT_SECRET")
    # Default to not requiring JWT in dev unless explicitly enabled
    require_jwt = os.getenv("REQUIRE_JWT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    optional_in_tests = os.getenv("JWT_OPTIONAL_IN_TESTS", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # Test-mode bypass: if running under pytest or explicit test flags, allow
    # anonymous access when no secret is configured. Mirrors the pattern used in
    # admin/test helpers and keeps kiosk endpoints usable in CI.
    is_test_mode = (
        os.getenv("ENV", "").lower() == "test"
        or optional_in_tests
        or os.getenv("PYTEST_RUNNING")
        or os.getenv("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or os.getenv("PYTEST_CURRENT_TEST")
    )
    if not secret and is_test_mode:
        secret = None
        require_jwt = False

    # Handle opaque session ID resolution for __session cookies
    if token and token_source in ["__session_cookie", "websocket_session_cookie"]:
        # For __session cookies, we expect an opaque session ID (never a JWT)
        # Use the canonical session resolver to get the JTI
        from ..session_store import get_session_store

        store = get_session_store()
        jti = store.get_session(token)

        if jti:
            # Found valid session, now get the access token to extract user_id
            access_token = None
            if request is not None:
                access_token = request.cookies.get("access_token")
            elif websocket is not None:
                try:
                    raw_cookie = websocket.headers.get("Cookie") or ""
                    parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
                    for p in parts:
                        if p.startswith("access_token="):
                            access_token = p.split("=", 1)[1]
                            break
                except Exception:
                    pass

            if access_token and secret:
                try:
                    # Decode the access token to get user_id (allow small skew)
                    payload = _jwt_decode(
                        access_token,
                        secret,
                        algorithms=["HS256"],
                        leeway=int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60),
                    )
                    user_id_from_token = payload.get("user_id") or payload.get("sub")

                    if user_id_from_token:
                        user_id = user_id_from_token
                        # Store JWT payload in request state for scope enforcement
                        if target and isinstance(payload, dict):
                            target.state.jwt_payload = payload
                        logger.info(
                            "auth.opaque_session_resolved",
                            extra={
                                "user_id": user_id,
                                "session_id": token,
                                "jti": jti,
                                "token_source": token_source,
                            },
                        )
                    else:
                        logger.warning(
                            "auth.opaque_session_no_user_id",
                            extra={
                                "session_id": token,
                                "jti": jti,
                                "token_source": token_source,
                            },
                        )
                except jwt.PyJWTError:
                    logger.warning(
                        "auth.opaque_session_token_decode_failed",
                        extra={
                            "session_id": token,
                            "jti": jti,
                            "token_source": token_source,
                        },
                    )
            else:
                logger.warning(
                    "auth.opaque_session_no_access_token",
                    extra={
                        "session_id": token,
                        "jti": jti,
                        "token_source": token_source,
                    },
                )
        else:
            logger.warning(
                "auth.opaque_session_invalid",
                extra={
                    "session_id": token,
                    "token_source": token_source,
                },
            )

    # Try traditional JWT first (same secret/issuer checks for both access_token and __session)
    if (
        not user_id
        and token
        and secret
        and token_source not in ["__session_cookie", "websocket_session_cookie"]
    ):
        try:
            # Enforce iss/aud in prod if configured
            opts = {}
            iss = os.getenv("JWT_ISSUER")
            aud = os.getenv("JWT_AUDIENCE")
            if iss:
                opts["issuer"] = iss
            if aud:
                opts["audience"] = aud

            if opts:
                payload = _jwt_decode(token, secret, algorithms=["HS256"], **opts)
            else:
                payload = _jwt_decode(token, secret, algorithms=["HS256"])

            user_id = payload.get("user_id") or payload.get("sub") or user_id

            # Store JWT payload in request state for scope enforcement
            if target and isinstance(payload, dict):
                target.state.jwt_payload = payload
        except jwt.PyJWTError:
            # For WebSocket handshakes, proceed as anonymous on invalid token to avoid
            # closing the connection before it's established. HTTP requests still fail.
            if websocket is None:
                try:
                    logger.warning(
                        "auth.invalid_token",
                        extra={"meta": {"reason": "invalid_auth_token"}},
                    )
                except Exception:
                    pass

                # Record auth failure metrics
                try:
                    from app.security import AUTH_FAIL

                    if AUTH_FAIL:
                        AUTH_FAIL.labels(reason="invalid").inc()
                except Exception:
                    pass

                raise HTTPException(
                    status_code=401, detail="Invalid authentication token"
                )
    elif token and not secret and require_jwt:
        # Token provided but no secret configured while required → fail-closed
        raise HTTPException(status_code=500, detail="missing_jwt_secret")

    # 5) Try Clerk authentication only if traditional JWT failed AND Clerk is enabled
    # AND the token source is NOT __session (unless Clerk is enabled)
    clerk_token = None
    if not user_id and token:
        # Only try Clerk validation if:
        # 1. Clerk is enabled, OR
        # 2. Token came from Authorization header (not __session cookie)
        clerk_enabled = _is_clerk_enabled()
        is_authorization_header = token_source == "authorization_header"
        is_session_cookie = token_source in [
            "__session_cookie",
            "websocket_session_cookie",
        ]

        # Never try to validate __session as a Clerk token unless Clerk is enabled
        if (clerk_enabled or is_authorization_header) and not (
            is_session_cookie and not clerk_enabled
        ):
            # Basic check if it looks like a Clerk JWT (has 3 parts separated by dots)
            if token.count(".") == 2:
                clerk_token = token

    if not user_id and clerk_token:
        try:
            from ..deps.clerk_auth import verify_clerk_token

            claims = verify_clerk_token(clerk_token)
            user_id = str(claims.get("sub") or claims.get("user_id") or "")

            # Store Clerk claims in request state for scope enforcement
            if target and isinstance(claims, dict):
                target.state.jwt_payload = claims
        except Exception:
            # For WebSocket handshakes, proceed as anonymous on invalid token
            if websocket is None:
                try:
                    logger.warning(
                        "auth.invalid_clerk_token",
                        extra={"meta": {"reason": "invalid_clerk_token"}},
                    )
                except Exception:
                    pass
                raise HTTPException(
                    status_code=401, detail="Invalid Clerk authentication token"
                )

    if not user_id:
        user_id = "anon"

        # Record metrics for missing/invalid tokens if we had a token but couldn't authenticate
        if (
            token and websocket is None
        ):  # Only for HTTP requests, not WebSocket handshakes
            try:
                from app.security import AUTH_FAIL

                if AUTH_FAIL:
                    AUTH_FAIL.labels(reason="missing").inc()
            except Exception:
                pass

    # Attach hashed ID to telemetry; keep raw on state when authenticated
    rec.user_id = hash_user_id(user_id) if user_id != "anon" else "anon"
    if target and user_id != "anon":
        target.state.user_id = user_id

    return user_id


async def require_user(request: Request) -> str:
    """FastAPI dependency that enforces a valid user authentication.

    Returns 401 if no valid authentication is found.
    On success, returns the user id.
    """
    # Skip CORS preflight requests
    if request.method == "OPTIONS":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        user_id = get_current_user_id(request=request)

        # If no valid user found, return 401
        if not user_id or user_id == "anon":
            raise HTTPException(status_code=401, detail="Unauthorized")

        return user_id
    except HTTPException:
        # Re-raise with consistent error message
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_current_session_device(
    request: Request | None = None, websocket: WebSocket | None = None
) -> dict:
    """Get session and device IDs using centralized resolution."""
    sid = resolve_session_id(request=request, websocket=websocket)
    target = request or websocket
    did = None
    try:
        if target is not None:
            did = target.headers.get("X-Device-ID")
        if not did and isinstance(request, Request):
            did = request.cookies.get("did")
        if not did and websocket is not None:
            did = websocket.query_params.get("did")
    except Exception:
        pass
    return {"session_id": sid, "device_id": did}


def resolve_session_id(
    request: Request | None = None,
    websocket: WebSocket | None = None,
    user_id: str | None = None,
) -> str:
    """
    Canonical function to resolve session ID consistently across the codebase.

    This function expects opaque session IDs from the __session cookie and provides
    a single representation and resolver for session management.

    Priority order:
    1. __session cookie (contains opaque session ID only, never JWT)
    2. X-Session-ID header (primary source for non-cookie scenarios)
    3. sid cookie (fallback)
    4. user_id from Authorization header (if available)
    5. user_id parameter (if provided and not None)
    6. "anon" (ultimate fallback)

    The __session cookie always contains an opaque session ID that maps to a JWT ID (JTI)
    in the session store. This ensures consistent session lifecycle management.
    """
    target = request or websocket

    # 1. Try __session cookie first (contains opaque session ID only)
    try:
        if isinstance(request, Request):
            session_id = request.cookies.get("__session") or request.cookies.get(
                "session"
            )
            if session_id:
                # Validate that this is an opaque session ID (not a JWT)
                if not session_id.count(".") == 2:  # JWT has 3 parts separated by dots
                    return session_id
                else:
                    logger.warning(
                        "auth.session_cookie_contains_jwt",
                        extra={
                            "session_id": session_id,
                        },
                    )
    except Exception:
        pass

    # 2. Try __session cookie for WebSocket handshakes
    try:
        if websocket is not None:
            raw_cookie = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("__session="):
                    session_id = p.split("=", 1)[1]
                    # Validate that this is an opaque session ID (not a JWT)
                    if (
                        not session_id.count(".") == 2
                    ):  # JWT has 3 parts separated by dots
                        return session_id
                    else:
                        logger.warning(
                            "auth.websocket_session_cookie_contains_jwt",
                            extra={
                                "session_id": session_id,
                            },
                        )
                    break
    except Exception:
        pass

    # 3. Try X-Session-ID header (primary source for non-cookie scenarios)
    try:
        if target is not None:
            sid = target.headers.get("X-Session-ID")
            if sid:
                return sid
    except Exception:
        pass

    # 4. Try sid cookie (fallback)
    try:
        if isinstance(request, Request):
            sid = request.cookies.get("sid")
            if sid:
                return sid
    except Exception:
        pass

    # 5. Try websocket query param
    try:
        if websocket is not None:
            sid = websocket.query_params.get("sid")
            if sid:
                return sid
    except Exception:
        pass

    # 6. Try to extract user_id from Authorization header
    try:
        if isinstance(request, Request):
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Remove "Bearer " prefix
                # Import here to avoid circular imports
                from ..api.auth import _decode_any

                payload = _decode_any(token)
                extracted_user_id = payload.get("sub") or payload.get("user_id")
                if extracted_user_id and extracted_user_id != "anon":
                    return extracted_user_id
    except Exception:
        pass

    # 7. Use provided user_id if available and not None
    if user_id is not None and user_id != "anon":
        return user_id

    # 8. Ultimate fallback
    return "anon"


__all__ = [
    "get_current_user_id",
    "get_current_session_device",
    "resolve_session_id",
    "require_user",
]
