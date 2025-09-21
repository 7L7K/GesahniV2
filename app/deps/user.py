from __future__ import annotations

import logging
import os
import time
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, Response, WebSocket

from app.web.cookies import clear_all_auth

log = logging.getLogger("auth")
logger = logging.getLogger(__name__)


async def _ensure_jwt_user_exists(user_id: str, request: Request) -> None:
    """Ensure JWT-authenticated users exist in the database.

    This is a critical gap-filler: JWT authentication works but doesn't provision users.
    We create users on-demand when they authenticate successfully.
    """
    # Only provision for JWT-authenticated users (not password users)
    # JWT user_ids are typically usernames, not UUIDs
    if not user_id or user_id == "anon":
        return

    # Skip if user already exists (fast path)
    # We check by trying to query the user - if it exists, we're done

    # Create the user (idempotent - handles existing users gracefully)
    try:
        from sqlalchemy.exc import IntegrityError

        from ..auth_store import create_user
        from ..util.ids import to_uuid

        # Convert username to UUID for database
        user_uuid = str(to_uuid(user_id))

        # Extract email from JWT claims if available
        email = f"{user_id}@jwt.local"  # Fallback email
        claims = getattr(request.state, "jwt_payload", None)
        if claims and isinstance(claims, dict):
            jwt_email = claims.get("email") or claims.get("preferred_username")
            if jwt_email and "@" in jwt_email:
                email = jwt_email

        await create_user(
            id=user_uuid,
            email=email,
            username=user_id,
            name=user_id,  # Use username as display name
        )

        log.info(
            "✅ JWT user provisioned",
            extra={
                "meta": {
                    "user_id": user_id,
                    "user_uuid": user_uuid,
                    "email": email,
                    "source": "jwt_provisioning",
                }
            },
        )

    except IntegrityError:
        # User already exists - this is expected and fine
        log.debug(
            "JWT user already exists",
            extra={"meta": {"user_id": user_id, "source": "jwt_provisioning"}},
        )
    except Exception as e:
        log.error(
            "❌ JWT user provisioning failed",
            extra={
                "meta": {
                    "user_id": user_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            },
        )
        # Don't fail the request - log and continue
        # This allows the app to work even if provisioning fails


try:
    from jose import jwt as jose_jwt
except Exception:
    jose_jwt = None

# Import decode_jwt from security module
try:
    import app.security as security_module

    decode_jwt = security_module.decode_jwt
except AttributeError:
    # Fallback: define decode_jwt locally if not available in module
    from app.security import jwt_decode
    from jwt import ExpiredSignatureError, PyJWTError

    from app.security.jwt_config import get_jwt_config

    def decode_jwt(token: str):
        cfg = get_jwt_config()
        try:
            if cfg.alg == "HS256":
                return jwt_decode(
                    token,
                    cfg.secret,
                    algorithms=["HS256"],
                    options={"verify_aud": bool(cfg.audience)},
                    audience=cfg.audience,
                    issuer=cfg.issuer,
                )
            else:
                headers = jwt.get_unverified_header(token)
                kid = headers.get("kid")
                if not kid or kid not in cfg.public_keys:
                    # Fallback: try any key to tolerate older tokens without kid
                    for k in cfg.public_keys.values():
                        try:
                            return jwt_decode(
                                token,
                                k,
                                algorithms=[cfg.alg],
                                options={"verify_aud": bool(cfg.audience)},
                                audience=cfg.audience,
                                issuer=cfg.issuer,
                            )
                        except Exception:
                            continue
                    return None
                key = cfg.public_keys[kid]
                return jwt_decode(
                    token,
                    key,
                    algorithms=[cfg.alg],
                    options={"verify_aud": bool(cfg.audience)},
                    audience=cfg.audience,
                    issuer=cfg.issuer,
                )
        except (ExpiredSignatureError, PyJWTError):
            return None


from ..telemetry import LogRecord, hash_user_id, log_record_var

JWT_SECRET: str | None = None  # overridden in tests; env used when None

logger = logging.getLogger(__name__)


def _decode_unverified(token: str) -> dict | None:
    if not token or not jose_jwt:
        return None
    try:
        if hasattr(jose_jwt, "get_unverified_claims"):
            return jose_jwt.get_unverified_claims(token)
        return jose_jwt.decode(token, "ignore", options={"verify_signature": False})
    except Exception:
        return None


def _is_clerk_enabled() -> bool:
    return False  # Clerk support removed


async def get_current_user_id(
    request: Request = None,
    websocket: WebSocket = None,
    response: Response = None,  # type: ignore[assignment]
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

    # OPTIMIZATION: Quick check for auth tokens to avoid expensive operations
    has_potential_auth = False

    # Check for Authorization header
    if target and target.headers.get("Authorization"):
        has_potential_auth = True

    # Check for auth cookies in request
    if not has_potential_auth and request:
        cookie_names = list(request.cookies.keys()) if hasattr(request, 'cookies') else []
        if any(name in ["GSNH_AT", "GSNH_SESS", "GSNH_RT", "access_token", "__session"] for name in cookie_names):
            has_potential_auth = True

    # Check for WS query params
    if not has_potential_auth and websocket:
        try:
            if websocket.query_params.get("access_token") or websocket.query_params.get("token"):
                has_potential_auth = True
        except Exception:
            pass

    # If no potential auth sources, return anon immediately without expensive operations
    if not has_potential_auth:
        return "anon"

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
                        "websocket_session_cookie"
                        if websocket is not None
                        else "__session_cookie"
                    )
        except Exception:
            pass

    # Cookie fallback so browser sessions persist without sending headers
    if token is None and request is not None:
        try:
            from ..web.cookies import ACCESS_ALIASES, get_any

            token = get_any(request, ACCESS_ALIASES)
            if token:
                token_source = "access_token_cookie"
        except Exception:
            token = None

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

    # 3) Try session cookie if access_token failed (contains opaque session ID only)
    if not token and request is not None:
        try:
            from ..web.cookies import read_session_cookie

            session_token = read_session_cookie(request)
        except Exception:
            session_token = None
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
                            if os.getenv(
                                "AUTH_LEGACY_COOKIE_NAMES", "1"
                            ).strip().lower() in {
                                "1",
                                "true",
                                "yes",
                                "on",
                            }:
                                logger.debug(
                                    "auth.legacy_cookie_used",
                                    extra={"meta": {"name": "__session"}},
                                )
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
                        "auth_header": (
                            bool(request.headers.get("Authorization"))
                            if request
                            else False
                        ),
                        "origin": request.headers.get("origin") if request else None,
                        "user_agent": (
                            request.headers.get("user-agent", "")[:50]
                            if request
                            else None
                        ),
                    },
                )
            else:
                logger.info(
                    "auth.no_token",
                    extra={
                        "request_path": request_path,
                        "all_cookies": list(request.cookies.keys()) if request else [],
                        "cookie_count": len(request.cookies) if request else 0,
                        "auth_header": (
                            bool(request.headers.get("Authorization"))
                            if request
                            else False
                        ),
                        "origin": request.headers.get("origin") if request else None,
                        "user_agent": (
                            request.headers.get("user-agent", "")[:50]
                            if request
                            else None
                        ),
                    },
                )
            # mark as logged for this request to avoid duplicate logs
            if target is not None:
                try:
                    target.state.auth_cookie_source_logged = True
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
        or os.getenv("PYTEST_RUNNING", "").strip().lower() in {"1", "true", "yes", "on"}
        or os.getenv("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or os.getenv("PYTEST_CURRENT_TEST")
    )
    if not secret and is_test_mode:
        secret = None
        require_jwt = False

    # Handle opaque session ID resolution for __session cookies (Identity-first)
    if token and token_source in ["__session_cookie", "websocket_session_cookie"]:
        from ..session_store import (
            SessionStoreUnavailable,
            get_session_store,
        )

        store = get_session_store()
        try:
            identity = store.get_session_identity(token)
        except SessionStoreUnavailable:
            # Flag for up-stack decision (503 on protected routes when session-only)
            try:
                if target is not None:
                    target.state.session_store_unavailable = True
                    target.state.session_cookie_present = True
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
                    target.state.auth_source = "session_identity"
                except Exception:
                    pass

            # Lazy refresh: Use the new auth_refresh module for robust token management
            try:
                if request is not None and response is not None:
                    from ..auth_refresh import perform_lazy_refresh
                    from ..metrics_auth import (
                        lazy_refresh_failed,
                        lazy_refresh_minted,
                        lazy_refresh_skipped,
                    )

                    if perform_lazy_refresh(request, response, user_id, identity):
                        lazy_refresh_minted("deps")
                    else:
                        lazy_refresh_skipped("deps")
            except Exception:
                # Best-effort; do not block auth
                try:
                    from ..metrics_auth import lazy_refresh_failed

                    lazy_refresh_failed("deps")
                except Exception:
                    pass
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
                        from ..web.cookies import read_access_cookie

                        access_token = read_access_cookie(request)
                    except Exception:
                        access_token = None
                elif websocket is not None:
                    try:
                        raw_cookie = websocket.headers.get("Cookie") or ""
                        parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
                        for p in parts:
                            if p.startswith("access_token="):
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
                        payload = decode_jwt(access_token)
                        uid = payload.get("user_id") or payload.get("sub")
                        if uid:
                            user_id = str(uid)
                            if target is not None:
                                target.state.jwt_payload = payload
                                target.state.auth_source = "session_backfill"
                            # Optionally write identity for future session-only auth
                            if os.getenv(
                                "AUTH_IDENTITY_BACKFILL", "1"
                            ).strip().lower() in {
                                "1",
                                "true",
                                "yes",
                                "on",
                            }:
                                try:
                                    exp_s = int(payload.get("exp"))
                                    store.set_session_identity(token, payload, exp_s)
                                except Exception:
                                    pass
                    except jose_jwt.JWTError:
                        pass

    # Try traditional JWT first using centralized decode
    if (
        not user_id
        and token
        and token_source not in ["__session_cookie", "websocket_session_cookie"]
    ):
        payload = decode_jwt(token)
        if payload:
            # Validate session if JWT contains session information
            if isinstance(payload, dict) and payload.get("sid"):
                try:
                    from app.sessions_store import sessions_store
                    sid = payload["sid"]
                    token_version = payload.get("sess_ver", 1)
                    jti = payload.get("jti", "")

                    is_valid, reason = await sessions_store.validate_session_token(
                        sid, token_version, jti
                    )

                    if not is_valid:
                        logger.warning(
                            f"Session validation failed for user {payload.get('sub')}: {reason}",
                            extra={"meta": {"reason": reason, "sid": sid, "jti": jti}}
                        )

                        # Return unauthorized for session validation failures
                        if reason in ["session.version_mismatch", "session.revoked", "token.blacklisted"]:
                            from app.http_errors import unauthorized
                            raise unauthorized(message=f"authentication failed: {reason}")

                        # For session.not_found, continue with JWT auth (might be older token)
                        pass

                except Exception as e:
                    logger.error(
                        f"Session validation error: {e}",
                        extra={"meta": {"error": str(e), "sid": payload.get("sid")}}
                    )
                    # Continue with JWT auth on validation errors (fail open for compatibility)

            user_id = payload.get("user_id") or payload.get("sub") or user_id

            # Store JWT payload in request state for scope enforcement
            if target and isinstance(payload, dict):
                target.state.jwt_payload = payload
        else:
            # Log signature failure for audit without leaking secrets
            if request is not None:
                ua = request.headers.get("user-agent", "-")
                ip = request.client.host if request.client else "-"
                log.info(
                    "auth.jwt_invalid: ip=%s ua=%s path=%s", ip, ua, request.url.path
                )

                # Clear auth cookies and return clean 401 on HTTP JWT failure
                if response is not None:
                    clear_all_auth(response)
                from app.http_errors import unauthorized

                raise unauthorized(message="invalid token")
            elif websocket is not None:
                # Log WebSocket auth failures but allow anonymous access
                ua = websocket.headers.get("user-agent", "-")
                log.info("auth.jwt_invalid_ws: ua=%s", ua)
                # WebSocket connections proceed as anonymous (current behavior)
    elif not token and request is not None:
        # Log missing token for audit
        ua = request.headers.get("user-agent", "-")
        ip = request.client.host if request.client else "-"
        log.info("auth.jwt_missing: ip=%s ua=%s path=%s", ip, ua, request.url.path)

        # Clear auth cookies and return clean 401 when token is missing
        if response is not None:
            clear_all_auth(response)
        from app.http_errors import unauthorized

        raise unauthorized(message="missing token")
    elif not token and websocket is not None:
        # Log missing token for WebSocket connections
        ua = websocket.headers.get("user-agent", "-")
        log.info("auth.jwt_missing_ws: ua=%s", ua)
    elif token and not secret and require_jwt:
        # Token provided but no secret configured while required → unauthorized, not 500
        from ..http_errors import unauthorized

        raise unauthorized(
            code="missing_jwt_secret",
            message="authentication required",
            hint="missing JWT secret configuration",
        )

    # Clerk validation removed

    if not user_id:
        # Try lazy refresh if we have a refresh cookie but no valid access token
        if request is not None and response is not None:
            try:
                from ..cookies import read_refresh_cookie

                refresh_token = read_refresh_cookie(request)
                if refresh_token:
                    from ..auth_refresh import perform_lazy_refresh
                    from ..metrics_auth import (
                        lazy_refresh_failed,
                        lazy_refresh_minted,
                        lazy_refresh_skipped,
                    )

                    # Extract user_id from refresh token for lazy refresh
                    try:
                        rt_payload = decode_jwt(refresh_token)
                        lazy_user_id = (
                            str(
                                rt_payload.get("sub") or rt_payload.get("user_id") or ""
                            )
                            if rt_payload
                            else ""
                        )
                    except Exception:
                        lazy_user_id = ""

                    if lazy_user_id and perform_lazy_refresh(
                        request, response, lazy_user_id, None
                    ):
                        lazy_refresh_minted("deps_fallback")
                        # After lazy refresh, try to authenticate with the new access token
                        try:
                            from ..cookies import read_access_cookie

                            new_access_token = read_access_cookie(request)
                            if new_access_token:
                                at_payload = decode_jwt(new_access_token)
                                if at_payload:
                                    user_id = str(
                                        at_payload.get("user_id")
                                        or at_payload.get("sub")
                                        or ""
                                    )
                                    if target and isinstance(at_payload, dict):
                                        target.state.jwt_payload = at_payload
                        except Exception:
                            pass
                    else:
                        lazy_refresh_skipped("deps_fallback")
            except Exception:
                try:
                    from ..metrics_auth import lazy_refresh_failed

                    lazy_refresh_failed("deps_fallback")
                except Exception:
                    pass

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


async def get_current_user_uuid(
    request: Request = None,
    websocket: WebSocket = None,
) -> UUID:
    """Return the current user's canonical UUID.

    This function extracts the JWT token, decodes it, and returns the canonical UUID
    from the 'sub' claim. For backward compatibility, it falls back to converting
    'user_id' or 'uid' claims to UUID using to_uuid().
    """
    # Get the raw user ID first
    user_id = await get_current_user_id(request=request, websocket=websocket)

    # If it's anon, return a special UUID for anonymous users
    if user_id == "anon":
        # Use a fixed UUID for anonymous users
        from app.util.ids import to_uuid
        return to_uuid("anon")

    # For authenticated users, extract the UUID from JWT claims
    target = request or websocket
    payload = getattr(target.state, "jwt_payload", None) if target else None

    if payload:
        # sub is the canonical UUID
        sub = payload.get("sub")
        if sub:
            try:
                return UUID(str(sub))
            except (ValueError, TypeError):
                # If sub isn't a valid UUID, convert it
                from app.util.ids import to_uuid
                return to_uuid(sub)

        # Backward compatible: check user_id or uid
        fallback_id = payload.get("user_id") or payload.get("uid")
        if fallback_id:
            from app.util.ids import to_uuid
            return to_uuid(fallback_id)

    # Fallback: convert the raw user_id
    from app.util.ids import to_uuid
    return to_uuid(user_id)


async def resolve_user_id(
    request: Request | None = None, websocket: WebSocket | None = None
) -> str:
    """Safe wrapper to resolve a user id from a Request or WebSocket.

    This helper catches exceptions and returns "anon" on failure so callers
    that cannot use FastAPI's `Depends` (middleware, internal helpers) can
    use a stable API.
    """
    try:
        return await get_current_user_id(request=request, websocket=websocket)
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
        user_id = await get_current_user_id(request=request)

        # If no valid user found, return 401 or 503 when session-only and store down
        if not user_id or user_id == "anon":
            st_unavail = getattr(request.state, "session_store_unavailable", False)
            sess_present = getattr(request.state, "session_cookie_present", False)
            if st_unavail and sess_present:
                raise HTTPException(status_code=503, detail="session_store_unavailable")
            from ..http_errors import unauthorized

            raise unauthorized(
                message="authentication required",
                hint="login or include Authorization header",
            )

        # Ensure JWT-authenticated users exist in database
        await _ensure_jwt_user_exists(user_id, request)

        return user_id
    except HTTPException:
        # Re-raise with consistent error message
        from ..http_errors import unauthorized

        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )


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
            from ..web.cookies import read_session_cookie

            session_id = read_session_cookie(request)
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

    # 6. Try to extract session ID from Authorization header
    try:
        if isinstance(request, Request):
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Remove "Bearer " prefix
                # Import here to avoid circular imports
                from ..api.auth import _decode_any

                payload = _decode_any(token)
                # Extract session ID (sid) from JWT payload, not user_id
                extracted_sid = payload.get("sid")
                if extracted_sid and extracted_sid != "anon":
                    return extracted_sid
    except Exception:
        pass
    
    # 6b. Try to extract session ID from access cookie
    try:
        if isinstance(request, Request):
            from ..web.cookies import read_access_cookie
            access_token = read_access_cookie(request)
            if access_token:
                # Import here to avoid circular imports
                from ..api.auth import _decode_any
                
                logger.info(f"🔍 RESOLVE_SESSION_ID_COOKIE: Found access cookie, attempting to decode", extra={
                    "meta": {
                        "token_length": len(access_token),
                        "timestamp": time.time()
                    }
                })
                
                payload = _decode_any(access_token)
                extracted_sid = payload.get("sid")
                
                logger.info(f"🔍 RESOLVE_SESSION_ID_COOKIE_RESULT: Decoded payload", extra={
                    "meta": {
                        "payload_keys": list(payload.keys()),
                        "extracted_sid": extracted_sid,
                        "has_sid": "sid" in payload,
                        "timestamp": time.time()
                    }
                })
                
                if extracted_sid and extracted_sid != "anon":
                    logger.info(f"🔍 RESOLVE_SESSION_ID_SUCCESS: Found valid session ID from cookie", extra={
                        "meta": {
                            "session_id": extracted_sid,
                            "timestamp": time.time()
                        }
                    })
                    return extracted_sid
    except Exception as e:
        logger.warning(f"🔍 RESOLVE_SESSION_ID_COOKIE_ERROR: Failed to decode access cookie", extra={
            "meta": {
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": time.time()
            }
        })
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
    try:
        if isinstance(request, Request):
            from ..web.cookies import read_session_cookie

            sid = read_session_cookie(request)
        elif websocket is not None:
            raw = websocket.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw.split(";") if p.strip()]
            for p in parts:
                if p.startswith("__Host-__session=") or p.startswith("__session="):
                    sid = p.split("=", 1)[1]
                    break
    except Exception:
        sid = None
    return sid


def resolve_auth_source_conflict(request: Request) -> tuple[str, bool]:
    """Resolve auth source with explicit Bearer-over-cookie precedence and detect conflicts.

    Returns a tuple (source, conflict) where source is one of:
    - "header" when Authorization: Bearer is present
    - "cookie" when an access token cookie is present
    - "session" when only a session cookie is present
    - "missing" when no auth material present

    Conflict flag returns True when both Authorization header and any auth cookie are present.
    """
    try:
        from ..web.cookies import NAMES as _COOKIE_NAMES
    except Exception:
        _COOKIE_NAMES = None  # type: ignore

    has_bearer = False
    try:
        auth = request.headers.get("Authorization") or ""
        has_bearer = auth.startswith("Bearer ")
    except Exception:
        has_bearer = False

    has_access_cookie = False
    has_session_cookie = False
    try:
        if _COOKIE_NAMES is not None:
            has_access_cookie = bool(request.cookies.get(_COOKIE_NAMES.access))
            has_session_cookie = bool(request.cookies.get(_COOKIE_NAMES.session))
        else:
            # Fallback to canonical names if import fails
            has_access_cookie = bool(request.cookies.get("GSNH_AT"))
            has_session_cookie = bool(request.cookies.get("GSNH_SESS"))
    except Exception:
        pass

    any_cookie = has_access_cookie or has_session_cookie
    conflict = bool(has_bearer and any_cookie)

    if has_bearer:
        return ("header", conflict)
    if has_access_cookie:
        return ("cookie", conflict)
    if has_session_cookie:
        return ("session", conflict)
    return ("missing", conflict)


__all__ = [
    "get_current_user_id",
    "get_current_user_uuid",
    "get_current_session_device",
    "resolve_session_id",
    "require_user",
    "resolve_user_id",
    "resolve_auth_source_conflict",
]
