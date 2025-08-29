from __future__ import annotations

import logging
import os
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request, WebSocket, Response

from ..security import _jwt_decode
from ..telemetry import LogRecord, hash_user_id, log_record_var

JWT_SECRET: str | None = None  # overridden in tests; env used when None

logger = logging.getLogger(__name__)


def _is_clerk_enabled() -> bool:
    return False  # Clerk support removed


def get_current_user_id(
    request: Request = None,
    websocket: WebSocket = None,
    response: Response | None = None,
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

    # Unified extraction via auth_core when no header/WS param token
    if token is None and target is not None:
        try:
            from ..auth_core import extract_token as _extract

            src, tok = _extract(target)
            if tok:
                token = tok
                if src == "authorization":
                    token_source = "authorization_header"
                elif src == "access_cookie":
                    token_source = "access_token_cookie"
                elif src == "session":
                    token_source = (
                        "websocket_session_cookie" if websocket is not None else "__session_cookie"
                    )
        except Exception:
            pass

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
            from ..cookie_names import GSNH_SESS, SESSION

            # Canonical first
            session_token = request.cookies.get(GSNH_SESS)
            if not session_token:
                # Legacy fallback (Phase 1 window)
                if os.getenv("AUTH_LEGACY_COOKIE_NAMES", "1").strip().lower() in {"1","true","yes","on"}:
                    session_token = request.cookies.get(SESSION) or request.cookies.get("session")
                    if session_token:
                        try:
                            logger.debug("auth.legacy_cookie_used", extra={"meta": {"name": SESSION}})
                        except Exception:
                            pass
        except Exception:
            session_token = request.cookies.get("session")
        if session_token:
            token = session_token
            token_source = "__session_cookie"

    # 4) Try __session cookie for WebSocket handshakes (canonical first)
    if not token and websocket is not None:
        try:
            raw_cookie = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("GSNH_SESS="):
                    token = p.split("=", 1)[1]
                    token_source = "websocket_session_cookie"
                    break
            if not token:
                # Legacy fallback for WS with DEBUG deprecation
                for p in parts:
                    if p.startswith("__session="):
                        token = p.split("=", 1)[1]
                        token_source = "websocket_session_cookie"
                        try:
                            if os.getenv("AUTH_LEGACY_COOKIE_NAMES", "1").strip().lower() in {"1","true","yes","on"}:
                                logger.debug("auth.legacy_cookie_used", extra={"meta": {"name": "__session"}})
                        except Exception:
                            pass
                        break
        except Exception:
            token = None

    # Enhanced logging for debugging auth issues
    try:
        logged_flag = None
        if target is not None:
            logged_flag = getattr(target.state, "auth_cookie_source_logged", None)
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
                    setattr(target.state, "auth_cookie_source_logged", True)
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

    # Handle opaque session ID resolution for __session cookies (Identity-first)
    if token and token_source in ["__session_cookie", "websocket_session_cookie"]:
        from ..session_store import (
            get_session_store,
            SessionStoreUnavailable,
        )

        store = get_session_store()
        try:
            identity = store.get_session_identity(token)
        except SessionStoreUnavailable:
            # Flag for up-stack decision (503 on protected routes when session-only)
            try:
                if target is not None:
                    setattr(target.state, "session_store_unavailable", True)
                    setattr(target.state, "session_cookie_present", True)
                    try:
                        from ..metrics import AUTH_STORE_OUTAGE

                        AUTH_STORE_OUTAGE.inc()
                    except Exception:
                        pass
            except Exception:
                pass
            identity = None

        if identity and isinstance(identity, dict):
            # Identity-first success
            user_id = str(identity.get("user_id") or identity.get("sub") or "")
            if target is not None:
                try:
                    target.state.jwt_payload = identity
                    setattr(target.state, "auth_source", "session_identity")
                except Exception:
                    pass

            # Lazy refresh: If we have a refresh token, and access token is missing or expiring soon, mint a new access
            try:
                if request is not None and response is not None:
                    from ..cookie_names import GSNH_RT, GSNH_AT, GSNH_SESS
                    from ..tokens import make_access
                    from ..cookie_config import get_token_ttls
                    from ..cookies import set_auth_cookies
                    from ..security import _jwt_decode
                    import time

                    rt = request.cookies.get(GSNH_RT)
                    at = request.cookies.get(GSNH_AT) or request.cookies.get("access_token")
                    if rt and os.getenv("JWT_SECRET"):
                        try:
                            rt_claims = _jwt_decode(
                                rt,
                                os.getenv("JWT_SECRET"),
                                algorithms=["HS256"],
                                leeway=int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60),
                            )
                            if str(rt_claims.get("type") or "") != "refresh":
                                rt_claims = None
                        except Exception:
                            rt_claims = None

                        if rt_claims:
                            # Helper for expiring soon with flag-configurable window
                            from ..flags import get_lazy_refresh_window_s

                            def _is_expiring_soon(payload: dict, window_s: int) -> bool:
                                try:
                                    exp = int(payload.get("exp", 0))
                                    return exp == 0 or (exp - int(time.time()) < window_s)
                                except Exception:
                                    return True

                            window = get_lazy_refresh_window_s()
                            exp_soon = (not at) or _is_expiring_soon(
                                getattr(target.state, "jwt_payload", {}) if target else {}, window
                            )
                            if exp_soon:
                                uid = str(rt_claims.get("sub") or rt_claims.get("user_id") or user_id)
                                access_ttl, _refresh_ttl = get_token_ttls()
                                new_at = make_access({"user_id": uid}, ttl_s=access_ttl)
                                # Keep RT unchanged; pass current session id for identity store continuity
                                sid = request.cookies.get(GSNH_SESS)
                                set_auth_cookies(
                                    response,
                                    access=new_at,
                                    refresh=None,
                                    session_id=sid,
                                    access_ttl=access_ttl,
                                    refresh_ttl=0,
                                    request=request,
                                    identity=identity or rt_claims,
                                )
                                try:
                                    from ..metrics import AUTH_LAZY_REFRESH

                                    AUTH_LAZY_REFRESH.labels(source="deps", result="minted").inc()
                                except Exception:
                                    pass
                            else:
                                try:
                                    from ..metrics import AUTH_LAZY_REFRESH

                                    AUTH_LAZY_REFRESH.labels(source="deps", result="skipped").inc()
                                except Exception:
                                    pass
            except Exception:
                # Best-effort; do not block auth
                pass
        else:
            # Backward-compat window: try legacy JTI mapping + access token backfill
            try:
                jti = store.get_session(token)
            except SessionStoreUnavailable:
                jti = None
            if jti and secret:
                access_token = None
                if request is not None:
                    try:
                        from ..cookie_names import GSNH_AT

                        access_token = request.cookies.get(GSNH_AT) or request.cookies.get("access_token")
                    except Exception:
                        access_token = request.cookies.get("access_token")
                elif websocket is not None:
                    try:
                        raw_cookie = websocket.headers.get("Cookie") or ""
                        parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
                        for p in parts:
                            if p.startswith("GSNH_AT="):
                                access_token = p.split("=", 1)[1]
                                break
                        if not access_token:
                            for p in parts:
                                if p.startswith("access_token="):
                                    access_token = p.split("=", 1)[1]
                                    break
                    except Exception:
                        pass

                if access_token:
                    try:
                        payload = _jwt_decode(
                            access_token,
                            secret,
                            algorithms=["HS256"],
                            leeway=int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60),
                        )
                        uid = payload.get("user_id") or payload.get("sub")
                        if uid:
                            user_id = str(uid)
                            if target is not None:
                                target.state.jwt_payload = payload
                                setattr(target.state, "auth_source", "session_backfill")
                            # Optionally write identity for future session-only auth
                            if os.getenv("AUTH_IDENTITY_BACKFILL", "1").strip().lower() in {"1","true","yes","on"}:
                                try:
                                    exp_s = int(payload.get("exp"))
                                    store.set_session_identity(token, payload, exp_s)
                                except Exception:
                                    pass
                    except jwt.PyJWTError:
                        pass

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

    # Clerk validation removed

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


def resolve_user_id(request: Request | None = None, websocket: WebSocket | None = None) -> str:
    """Safe wrapper to resolve a user id from a Request or WebSocket.

    This helper catches exceptions and returns "anon" on failure so callers
    that cannot use FastAPI's `Depends` (middleware, internal helpers) can
    use a stable API.
    """
    try:
        return get_current_user_id(request=request, websocket=websocket)
    except Exception:
        return "anon"


async def require_user(request: Request) -> str:
    """FastAPI dependency that enforces a valid user authentication.

    Returns 401 if no valid authentication is found.
    On success, returns the user id.
    """
    # Skip CORS preflight requests (never 401 on OPTIONS)
    if request.method == "OPTIONS":
        return "anon"

    try:
        user_id = get_current_user_id(request=request)

        # If no valid user found, return 401 or 503 when session-only and store down
        if not user_id or user_id == "anon":
            st_unavail = getattr(request.state, "session_store_unavailable", False)
            sess_present = getattr(request.state, "session_cookie_present", False)
            if st_unavail and sess_present:
                raise HTTPException(status_code=503, detail="session_store_unavailable")
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


def resolve_session_id_strict(
    request: Request | None = None, websocket: WebSocket | None = None
) -> str | None:
    """Strict resolver: returns None when not found or invalid.

    Deprecation path: callers should migrate from resolve_session_id() to this.
    """
    sid = None
    target = request or websocket
    try:
        if isinstance(request, Request):
            from ..cookie_names import GSNH_SESS

            sid = request.cookies.get(f"__Host-{GSNH_SESS}") or request.cookies.get(GSNH_SESS)
        elif websocket is not None:
            raw = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw.split(";") if p.strip()]
            for p in parts:
                if p.startswith("__Host-GSNH_SESS=") or p.startswith("GSNH_SESS="):
                    sid = p.split("=", 1)[1]
                    break
    except Exception:
        sid = None
    return sid


__all__ = [
    "get_current_user_id",
    "get_current_session_device",
    "resolve_session_id",
    "require_user",
    "resolve_user_id",
]
