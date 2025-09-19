from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import secrets
import time
import warnings
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth_protection import public_route

# DEPRECATED: Import from app.auth.endpoints.* instead
warnings.warn(
    "DEPRECATED: app.api.auth is deprecated. Import from app.auth.endpoints.* instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Legacy re-exports - these will be wrapped with deprecation warnings below
from app.auth.endpoints.debug import debug_auth_state, debug_cookies, whoami
from app.auth.endpoints.login import login, login_v1
from app.auth.endpoints.logout import logout, logout_all
from app.auth.endpoints.refresh import refresh, rotate_refresh_cookies
from app.auth.endpoints.register import register_v1
from app.auth.endpoints.token import dev_token, token_examples

from ..deps.scopes import require_scope
from ..deps.user import get_current_user_id, require_user, resolve_session_id
from ..security import jwt_decode
from app.session_store import new_session_id

require_user_clerk = None  # Clerk removed
from fastapi.responses import JSONResponse

from app.auth_debug import log_incoming_cookies, log_set_cookie

from ..auth_monitoring import record_whoami_call, track_auth_event
from ..auth_store import create_pat as _create_pat
from ..auth_store import get_pat_by_hash as _get_pat_by_hash
from ..logging_config import req_id_var
from ..metrics import WHOAMI_FAIL, WHOAMI_OK
from ..models.user import get_user_async
from ..token_store import (
    allow_refresh,
)
from ..user_store import user_store


# Debug dependency for auth endpoints
async def log_request_meta(request: Request):
    """Log detailed request metadata for debugging auth issues."""
    cookies = list(request.cookies.keys())
    origin = request.headers.get("origin", "none")
    referer = request.headers.get("referer", "none")
    user_agent = request.headers.get("user-agent", "none")
    content_type = request.headers.get("content-type", "none")

    logger.info(
        "🔐 AUTH REQUEST DEBUG",
        extra={
            "meta": {
                "path": request.url.path,
                "method": request.method,
                "origin": origin,
                "referer": referer,
                "user_agent": (
                    user_agent[:100] + "..."
                    if user_agent and len(user_agent) > 100
                    else user_agent
                ),
                "content_type": content_type,
                "cookies_present": len(cookies) > 0,
                "cookie_names": cookies,
                "cookie_count": len(cookies),
                "has_auth_header": "authorization"
                in [h.lower() for h in request.headers.keys()],
                "query_params": dict(request.query_params),
                "client_ip": (
                    getattr(request.client, "host", "unknown")
                    if request.client
                    else "unknown"
                ),
            }
        },
    )

    return request


router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
logger = logging.getLogger(__name__)
# Auth metrics are now handled by Prometheus counters in app.metrics


class RefreshOut(BaseModel):
    rotated: bool
    access_token: str | None = None
    user_id: str | None = None
    csrf: str | None = None
    csrf_token: str | None = None


def _decode_any(token: str) -> dict | None:
    try:
        return jwt_decode(token, _jwt_secret(), algorithms=["HS256"])  # type: ignore[arg-type]
    except Exception:
        try:
            return jwt_decode(token, _jwt_secret(), algorithms=["HS256"])  # type: ignore[arg-type]
        except Exception:
            return None


def _append_legacy_auth_cookie_headers(
    response: Response,
    *,
    access: str | None,
    refresh: str | None,
    session_id: str | None,
    request: Request,
) -> None:
    """Append legacy cookie names (access_token, refresh_token, __session) with config flags.

    Keeps unit-level web.set_auth_cookies canonical-only, while endpoints provide
    compatibility for tests/clients expecting legacy names.

    Controlled by AUTH_LEGACY_COOKIE_NAMES environment variable.
    """
    # Check if legacy cookie names are enabled
    if os.getenv("AUTH_LEGACY_COOKIE_NAMES", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return  # Skip writing legacy cookies

    try:
        from ..cookie_config import format_cookie_header, get_cookie_config

        cfg = get_cookie_config(request)
        ss = str(cfg.get("samesite", "lax")).capitalize()
        dom = cfg.get("domain")
        path = cfg.get("path", "/")
        sec = bool(cfg.get("secure", True))
        if access:
            response.headers.append(
                "set-cookie",
                format_cookie_header(
                    "access_token",
                    access,
                    max_age=int(cfg.get("access_ttl", 1800)),
                    secure=sec,
                    samesite=ss,
                    path=path,
                    httponly=True,
                    domain=dom,
                ),
            )
        if refresh:
            response.headers.append(
                "set-cookie",
                format_cookie_header(
                    "refresh_token",
                    refresh,
                    max_age=int(cfg.get("refresh_ttl", 86400)),
                    secure=sec,
                    samesite=ss,
                    path=path,
                    httponly=True,
                    domain=dom,
                ),
            )
        if session_id:
            response.headers.append(
                "set-cookie",
                format_cookie_header(
                    "__session",
                    session_id,
                    max_age=int(cfg.get("access_ttl", 1800)),
                    secure=sec,
                    samesite=ss,
                    path=path,
                    httponly=True,
                    domain=dom,
                ),
            )
    except Exception as e:
        logger.warning(
            "auth_flow: legacy_cookie_header_error=true, error=%s",
            str(e),
            exc_info=True,
        )


def _is_rate_limit_enabled() -> bool:
    """Return True when in-app endpoint rate limits should apply.

    Disabled by default in test unless explicitly enabled, and always disabled
    when RATE_LIMIT_MODE=off.
    """
    try:
        v = (os.getenv("RATE_LIMIT_MODE") or "").strip().lower()
        if v == "off":
            return False
        in_test = (os.getenv("ENV", "").strip().lower() == "test") or bool(
            os.getenv("PYTEST_RUNNING") or os.getenv("PYTEST_CURRENT_TEST")
        )
        if in_test and (
            os.getenv("ENABLE_RATE_LIMIT_IN_TESTS", "0").strip().lower()
            not in {"1", "true", "yes", "on"}
        ):
            return False
    except Exception as e:
        logger.warning(
            "rate_limit_config: config_error=true, error=%s", str(e), exc_info=True
        )
    return True


def _append_cookie_with_priority(
    response: Response,
    *,
    key: str,
    value: str,
    max_age: int,
    secure: bool,
    samesite: str,
    path: str = "/",
    domain: str = None,
) -> None:
    """Append a cookie header with priority using the centralized cookie configuration.

    This function should be replaced with calls to the centralized cookie facade
    in app/cookies.py. This is a legacy function that will be removed.
    """
    # This function is deprecated and should not be used.
    # Use the centralized cookie functions from app/cookies.py instead.
    # For example: set_named_cookie(), set_auth_cookies(), etc.
    raise DeprecationWarning(
        "_append_cookie_with_priority is deprecated. Use centralized cookie functions from app/cookies.py"
    )


# Clerk endpoints removed


def should_rotate_access(user_id: str) -> bool:
    """
    Determine if access token should be rotated based on user ID and rotation policy.

    This function implements the guard against accidental clearing by ensuring
    rotation decisions are explicit and safe.

    Args:
        user_id: The user ID for whom rotation is being considered

    Returns:
        True if rotation should proceed, False otherwise
    """
    # Default policy: rotate for authenticated users unless explicitly disabled
    # This can be extended with more sophisticated logic based on user attributes,
    # session state, or other factors
    return bool(user_id and user_id != "anon")


def mint_access_token(user_id: str) -> str:
    """
    Mint a new access token with guard against empty tokens.

    This function ensures that empty or invalid tokens are never created,
    preventing accidental cookie clearing.

    Args:
        user_id: The user ID for whom to mint the token

    Returns:
        A valid JWT access token string

    Raises:
        HTTPException: If token creation would result in an empty or invalid token
    """
    if not user_id or user_id == "anon":
        raise HTTPException(
            status_code=500, detail="cannot_mint_token_for_invalid_user"
        )

    try:
        from ..cookie_config import get_token_ttls
        from ..tokens import make_access

        access_ttl, _ = get_token_ttls()
        token = make_access({"user_id": user_id}, ttl_s=access_ttl)

        # Guard against empty tokens
        if not token or not isinstance(token, str) or len(token.strip()) == 0:
            logger.error(f"Empty token generated for user {user_id}")
            raise HTTPException(status_code=500, detail="token_generation_failed")

        return token
    except Exception as e:
        logger.error(f"Token minting failed for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="token_generation_failed") from e


@router.get("/debug/cookies")
def debug_cookies(request: Request) -> dict[str, dict[str, str]]:
    """Echo cookie presence for debugging (values not exposed).

    Returns a mapping of cookie names to "present"/empty string so callers can
    determine whether the browser attached cookies on this request.
    """
    try:
        cookies = {
            k: ("present" if (v is not None and v != "") else "")
            for k, v in request.cookies.items()
        }
    except Exception:
        cookies = {}
    return {"cookies": cookies}


@router.get("/debug/auth-state")
def debug_auth_state(request: Request) -> dict[str, Any]:
    """Debug auth state - shows cookies received and token validation status.

    Returns comprehensive auth debugging info including:
    - All cookies received by name
    - Whether access/refresh/session cookies are present and valid
    - Current authentication status
    """
    try:
        # Import cookie readers
        from ..cookies import (
            read_access_cookie,
            read_refresh_cookie,
            read_session_cookie,
        )

        # Read tokens from cookies
        access = read_access_cookie(request)
        refresh = read_refresh_cookie(request)
        session = read_session_cookie(request)

        # Check if tokens are valid (basic decode check)
        access_valid = False
        refresh_valid = False
        session_valid = bool(session)  # Session is just an opaque string

        if access:
            try:
                _decode_any(access)
                access_valid = True
            except Exception as e:
                logger.warning(
                    "debug_auth_state: access_token_decode_error=true, error=%s",
                    str(e),
                    exc_info=True,
                )

        if refresh:
            try:
                _decode_any(refresh)
                refresh_valid = True
            except Exception as e:
                logger.warning(
                    "debug_auth_state: refresh_token_decode_error=true, error=%s",
                    str(e),
                    exc_info=True,
                )

        return {
            "cookies_seen": list(request.cookies.keys()),
            "has_access": bool(access),
            "has_refresh": bool(refresh),
            "has_session": bool(session),
            "access_valid": access_valid,
            "refresh_valid": refresh_valid,
            "session_valid": session_valid,
            "cookie_count": len(request.cookies),
        }
    except Exception as e:
        return {
            "error": str(e),
            "cookies_seen": (
                list(request.cookies.keys()) if hasattr(request, "cookies") else []
            ),
            "has_access": False,
            "has_refresh": False,
            "has_session": False,
        }


def _in_test_mode() -> bool:
    def v(s):
        return str(os.getenv(s, "")).strip().lower()

    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("PYTEST_RUNNING")
        or v("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or v("ENV") == "test"
    )


def _ensure_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        # Only create a loop automatically in test contexts
        if (
            os.getenv("PYTEST_CURRENT_TEST")
            or os.getenv("PYTEST_RUNNING")
            or os.getenv("ENV", "").lower() == "test"
        ):
            asyncio.set_event_loop(asyncio.new_event_loop())


# Ensure a default loop exists when imported under pytest to support
# synchronous helpers that need to spin async functions.
if _in_test_mode():
    _ensure_loop()


async def _require_user_or_dev(request: Request) -> str:
    """Require Clerk user when configured; allow dev fallback when enabled.

    Fallback is enabled when either of the following is true:
    - AUTH_DEV_BYPASS in {1,true,yes,on}
    - ENV is dev and CLERK_* not configured (best-effort)
    """
    # Explicit bypass knob for local testing
    if os.getenv("AUTH_DEV_BYPASS", "0").strip().lower() in {"1", "true", "yes", "on"}:
        return os.getenv("DEV_USER_ID", "dev")
    # Try Clerk first
    try:
        return await require_user(request)
    except Exception:
        # Best-effort dev fallback when Clerk isn't configured and we're in dev
        env = os.getenv("ENV", "dev").strip().lower()
        has_clerk = any(
            bool(os.getenv(k, "").strip())
            for k in ("CLERK_JWKS_URL", "CLERK_ISSUER", "CLERK_DOMAIN")
        )
        if env in {"dev", "development"} and not has_clerk:
            return os.getenv("DEV_USER_ID", "dev")
        # Otherwise, re-raise unauthorized

        from ..http_errors import unauthorized as _unauth

        raise _unauth(
            message="authentication required",
            hint="login or include Authorization header",
        )


async def verify_pat_async(
    token: str, required_scopes: list[str] | None = None
) -> dict[str, Any] | None:
    """Async version of verify_pat for use in API handlers."""
    try:
        import hashlib

        h = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
        rec = await _get_pat_by_hash(h)
        if not rec:
            return None
        if rec.get("revoked_at"):
            return None
        scopes = set(rec.get("scopes") or [])
        if required_scopes and not set(required_scopes).issubset(scopes):
            return None
        return rec
    except Exception:
        return None


def verify_pat(
    token: str, required_scopes: list[str] | None = None
) -> dict[str, Any] | None:
    """Synchronous version of verify_pat for backward compatibility."""
    try:
        import hashlib

        h = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
        # Fetch synchronously via event loop since tests call this directly
        _ensure_loop()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In case an event loop is already running, fall back to None (not expected in unit)
                return None
            rec = loop.run_until_complete(_get_pat_by_hash(h))  # type: ignore[arg-type]
        except RuntimeError:
            rec = asyncio.run(_get_pat_by_hash(h))  # type: ignore[arg-type]
        if not rec:
            return None
        if rec.get("revoked_at"):
            return None
        scopes = set(rec.get("scopes") or [])
        if required_scopes and not set(required_scopes).issubset(scopes):
            return None
        return rec
    except Exception:
        return None


async def whoami_impl(request: Request) -> dict[str, Any]:
    """Canonical whoami implementation: single source of truth for session readiness.

    Response shape (versioned):
    {
      "is_authenticated": bool,
      "session_ready": bool,
      "user": { "id": str, "email": str | None },
      "source": "cookie" | "header" | "clerk" | "missing",
      "version": 1
    }
    """
    import logging

    logger = logging.getLogger(__name__)

    with track_auth_event("whoami", user_id="unknown"):
        t0 = time.time()
        src: str = "missing"
        token_cookie: str | None = None
        token_header: str | None = None
        clerk_token: str | None = None

        logger.info(
            "🔍 WHOAMI_IMPL_START: Starting whoami implementation",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "ip": request.client.host if request.client else "unknown",
                    "user_agent": request.headers.get("User-Agent", "unknown"),
                    "cookies_present": list(request.cookies.keys()),
                    "auth_header_present": "authorization" in [h.lower() for h in request.headers.keys()],
                    "timestamp": time.time(),
                }
            },
        )

    try:
        # Prefer canonical cookie name but accept legacy for migration
        # Accept canonical and legacy access cookie names via centralized reader
        from ..cookies import read_access_cookie

        token_cookie = read_access_cookie(request)
        logger.info(
            "🔍 WHOAMI_COOKIE_CHECK: Checking for access token cookie",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "has_access_token_cookie": bool(token_cookie),
                    "cookie_length": len(token_cookie) if token_cookie else 0,
                    "cookie_count": len(request.cookies),
                    "cookie_names": list(request.cookies.keys()),
                    "timestamp": time.time(),
                }
            },
        )
    except Exception as e:
        logger.error(
            "whoami.cookie_error",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": time.time(),
                }
            },
        )
        token_cookie = None

    try:
        ah = request.headers.get("Authorization")
        if ah and ah.startswith("Bearer "):
            token_header = ah.split(" ", 1)[1]
        logger.info(
            "whoami.header_check",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "has_authorization_header": bool(ah),
                    "starts_with_bearer": ah.startswith("Bearer ") if ah else False,
                    "has_token_header": bool(token_header),
                    "token_header_length": len(token_header) if token_header else 0,
                    "timestamp": time.time(),
                }
            },
        )
    except Exception as e:
        logger.error(
            "whoami.header_error",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": time.time(),
                }
            },
        )
        token_header = None

    # Clerk checks removed
    clerk_token = None

    # Prefer cookie when valid; otherwise fall back to header; then try Clerk
    session_ready = False
    effective_uid: str | None = None
    jwt_status = "missing"

    # Priority 1: Try access_token cookie first (most secure)
    # Set source to "cookie" if we have a cookie token, even if invalid
    if token_cookie:
        src = "cookie"  # Cookie has priority over header
        try:
            logger.info(
                "whoami.cookie_jwt_decode.start",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "timestamp": time.time(),
                    }
                },
            )
            # Allow a small clock skew when decoding cookies (iat/nbf)
            claims = _decode_any(token_cookie)
            session_ready = True
            effective_uid = (
                str(claims.get("user_id") or claims.get("sub") or "") or None
            )
            jwt_status = "ok"
            logger.info(
                "🔍 WHOAMI_JWT_DECODE_SUCCESS: Cookie JWT decoded successfully",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "user_id": effective_uid,
                        "claims_keys": list(claims.keys()),
                        "claims_data": claims,
                        "jwt_status": jwt_status,
                        "source": "cookie",
                        "timestamp": time.time(),
                    }
                },
            )
        except Exception as e:
            session_ready = False
            effective_uid = None
            jwt_status = "invalid"
            logger.error(
                "🔍 WHOAMI_JWT_DECODE_FAILED: Cookie JWT decode failed",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "token_length": len(token_cookie) if token_cookie else 0,
                        "source": "cookie",
                        "timestamp": time.time(),
                    }
                },
            )

    # Priority 2: Try Authorization header if cookie failed or missing
    if not session_ready and token_header:
        src = "header"
        try:
            logger.info(
                "whoami.header_jwt_decode.start",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "timestamp": time.time(),
                    }
                },
            )
            # Allow a small clock skew when decoding headers (iat/nbf)
            claims = _decode_any(token_header)
            session_ready = True
            effective_uid = (
                str(claims.get("user_id") or claims.get("sub") or "") or None
            )
            jwt_status = "ok"
            logger.info(
                "whoami.header_jwt_decode.success",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "user_id": effective_uid,
                        "claims_keys": list(claims.keys()),
                        "timestamp": time.time(),
                    }
                },
            )
        except Exception as e:
            session_ready = False
            effective_uid = None
            jwt_status = "invalid"
            logger.error(
                "whoami.header_jwt_decode.failed",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "timestamp": time.time(),
                    }
                },
            )

    # Priority 3: Try Clerk verification if both header and cookie failed and Clerk is enabled
    if not session_ready and clerk_token and os.getenv("CLERK_ENABLED", "0") == "1":
        try:
            logger.info(
                "whoami.clerk_verification.start",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "timestamp": time.time(),
                    }
                },
            )

            # Try to verify Clerk token using the proper Clerk verification
            try:
                from ..deps.clerk_auth import verify_clerk_token as _verify_clerk

                if _verify_clerk:
                    clerk_claims = _verify_clerk(clerk_token)
                    effective_uid = clerk_claims.get("user_id") or clerk_claims.get(
                        "sub"
                    )
                    if effective_uid:
                        session_ready = True
                        src = "clerk"
                        jwt_status = "ok"
                        logger.info(
                            "whoami.clerk_verification.success",
                            extra={
                                "meta": {
                                    "req_id": req_id_var.get(),
                                    "user_id": effective_uid,
                                    "timestamp": time.time(),
                                }
                            },
                        )
                else:
                    logger.warning(
                        "whoami.clerk_verification.no_verifier",
                        extra={
                            "meta": {
                                "req_id": req_id_var.get(),
                                "timestamp": time.time(),
                            }
                        },
                    )
            except ImportError:
                logger.warning(
                    "whoami.clerk_verification.not_available",
                    extra={
                        "meta": {
                            "req_id": req_id_var.get(),
                            "timestamp": time.time(),
                        }
                    },
                )
            except Exception as e:
                logger.warning(
                    "whoami.clerk_verification.invalid",
                    extra={
                        "meta": {
                            "req_id": req_id_var.get(),
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "timestamp": time.time(),
                        }
                    },
                )
        except Exception as e:
            logger.error(
                "whoami.clerk_verification.failed",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "timestamp": time.time(),
                    }
                },
            )

    # (Duplicate header decode removed; header is already tried above)

    # (Duplicate Clerk verification blocks removed; single Clerk path retained above)

    # Canonical policy: authenticated iff a valid token was presented
    is_authenticated = bool(session_ready and effective_uid)

    logger.info(
        "🔍 WHOAMI_RESULT: Final whoami result",
        extra={
            "meta": {
                "req_id": req_id_var.get(),
                "is_authenticated": is_authenticated,
                "session_ready": session_ready,
                "source": src,
                "user_id": effective_uid,
                "jwt_status": jwt_status,
                "token_cookie_present": bool(token_cookie),
                "token_header_present": bool(token_header),
                "clerk_token_present": bool(clerk_token),
                "timestamp": time.time(),
            }
        },
    )

    # Log a compact line for probing and metrics
    try:
        dt = int((time.time() - t0) * 1000)
        logger.info(
            "whoami t=%dms jwt=%s src=%s",
            dt,
            jwt_status,
            src,
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "duration_ms": dt,
                    "jwt_status": jwt_status,
                    "source": src,
                }
            },
        )
        try:
            if session_ready:
                WHOAMI_OK.inc()
            else:
                WHOAMI_FAIL.labels(reason="jwt_invalid").inc()
        except Exception as e:
            logger.warning(
                "whoami: metrics_error=true, error=%s", str(e), exc_info=True
            )
    except Exception as e:
        logger.warning("whoami: logging_error=true, error=%s", str(e), exc_info=True)

    # Record whoami call for monitoring
    try:
        record_whoami_call(
            status="success",
            source=src,
            user_id=effective_uid,
            session_ready=session_ready,
            is_authenticated=is_authenticated,
            jwt_status=jwt_status,
        )
    except Exception as e:
        logger.warning(
            "whoami: record_call_error=true, error=%s", str(e), exc_info=True
        )

    # For public whoami endpoint, return success even when unauthenticated
    # This allows clients to check authentication status without requiring auth
    has_any_token = bool(token_header or token_cookie or clerk_token)
    if not has_any_token or (has_any_token and not session_ready):
        # Return successful response with unauthenticated state
        from fastapi.responses import JSONResponse as _JSON

        from ..logging_config import req_id_var as _rid

        body = {
            "is_authenticated": False,
            "session_ready": False,
            "user": {"id": None, "email": None},
            "source": "missing",
            "version": 1,
            "request_id": _rid.get(),
        }
        resp = _JSON(body, status_code=200)
        resp.headers.setdefault("Cache-Control", "no-store, max-age=0")
        resp.headers.setdefault("Pragma", "no-cache")
        resp.headers.setdefault("Expires", "0")
        # Add CORS headers for better frontend compatibility
        resp.headers.setdefault("Access-Control-Allow-Credentials", "true")
        if _rid.get():
            resp.headers.setdefault("X-Request-ID", _rid.get())
        return resp

    # Prefer Bearer when both header and cookies are present; detect conflict
    try:
        from ..deps.user import resolve_auth_source_conflict as _resolve_src

        src2, conflict = _resolve_src(request)
    except Exception:
        src2, conflict = src, False
    if src2:
        src = src2

    from ..logging_config import req_id_var as _rid

    body = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "request_id": _rid.get(),
        "is_authenticated": bool(is_authenticated),
        "session_ready": bool(session_ready),
        "user_id": effective_uid if effective_uid else None,
        "user": {
            "id": effective_uid if effective_uid else None,
            "email": getattr(request.state, "email", None),
        },
        "source": src,
        "version": 1,
    }
    dbg = (os.getenv("DEBUG") or "").strip().lower() in {"1", "true", "yes", "on"}
    legacy = (os.getenv("CSRF_LEGACY_GRACE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if conflict and (dbg or legacy):
        body["auth_source_conflict"] = True
    # Log conflict warning always
    if conflict:
        try:
            logger.warning(
                "auth.source_conflict user_id=%s request_id=%s",
                body.get("user_id"),
                _rid.get(),
            )
        except Exception as e:
            logger.error(
                "whoami: source_conflict_log_error=true, error=%s",
                str(e),
                exc_info=True,
            )

    # Observability log
    try:
        latency_ms = int((time.time() - t0) * 1000)
        logger.info(
            "evt=identity_check route=/v1/whoami user_id=%s source=%s is_authenticated=%s request_id=%s latency_ms=%d",
            body.get("user_id"),
            src,
            body.get("is_authenticated"),
            _rid.get(),
            latency_ms,
        )
    except Exception as e:
        logger.error(
            "whoami: observability_log_error=true, error=%s", str(e), exc_info=True
        )

    from fastapi.responses import JSONResponse as _JSON

    resp = _JSON(body, status_code=200)
    resp.headers.setdefault("Cache-Control", "no-store, max-age=0")
    resp.headers.setdefault("Pragma", "no-cache")
    resp.headers.setdefault("Expires", "0")
    # Add CORS headers for better frontend compatibility
    resp.headers.setdefault("Access-Control-Allow-Credentials", "true")
    if _rid.get():
        resp.headers.setdefault("X-Request-ID", _rid.get())
    return resp


@router.get("/whoami", include_in_schema=False)
async def whoami(
    request: Request, response: Response, _: None = Depends(log_request_meta)
) -> JSONResponse:
    """CANONICAL: Public whoami endpoint - the single source of truth for user identity.

    This is the canonical whoami endpoint that should be used by all clients.
    Returns comprehensive authentication and session information including:

    - Authentication status and session readiness
    - User information (ID and email)
    - Authentication source (cookie, header, clerk, or missing)
    - API version for future compatibility

    Response schema:
    {
      "is_authenticated": bool,
      "session_ready": bool,
      "user_id": str | null,
      "user": {"id": str | null, "email": str | null},
      "source": "cookie" | "header" | "clerk" | "missing",
      "version": 1
    }
    """
    start_time = time.time()
    req_id = req_id_var.get()
    
    logger.info(f"🔍 WHOAMI_START: Request received", extra={
        "meta": {
            "req_id": req_id,
            "timestamp": start_time,
            "cookies_count": len(request.cookies),
            "has_auth_header": "authorization" in [h.lower() for h in request.headers.keys()],
            "user_agent": request.headers.get("user-agent", "")[:100]
        }
    })

    # Optional debug: log incoming cookie presence
    try:
        if os.getenv("AUTH_DEBUG") == "1":
            log_incoming_cookies(request, route="/v1/whoami")
    except Exception as e:
        logger.warning("whoami: debug_log_error=true, error=%s", str(e), exc_info=True)

    # First, delegate identity resolution to canonical whoami_impl
    try:
        out = await whoami_impl(request)
    except Exception as e:
        # Allow HTTPException to propagate for proper error responses
        from fastapi import HTTPException

        if isinstance(e, HTTPException):
            raise e
        # For other exceptions, return unauthenticated response
        out = {
            "is_authenticated": False,
            "session_ready": False,
            "user": None,
            "session": None,
            "source": "missing",
            "version": 1,
        }

    # If whoami_impl returned a Response, optionally perform lazy refresh on 401 then pass through
    from fastapi.responses import Response as _RespType

    if isinstance(out, _RespType):  # type: ignore[arg-type]
        try:
            # When unauthenticated but a refresh cookie is present, mint a new access token
            if getattr(out, "status_code", None) == 401:
                from ..cookies import read_access_cookie, read_refresh_cookie

                access_cookie = read_access_cookie(request)
                has_refresh = bool(read_refresh_cookie(request))
                if not access_cookie and has_refresh:
                    try:
                        from ..auth_refresh import perform_lazy_refresh
                        from ..deps.user import get_current_user_id

                        current_user_id = get_current_user_id(request=request)
                        await perform_lazy_refresh(request, out, current_user_id)  # type: ignore[arg-type]
                    except Exception as e:
                        logger.warning(
                            "whoami: lazy_refresh_error=true, error=%s",
                            str(e),
                            exc_info=True,
                        )
        except Exception as e:
            logger.warning(
                "whoami: lazy_refresh_setup_error=true, error=%s", str(e), exc_info=True
            )
        return out  # type: ignore[return-value]

    # If already authenticated (dict), return immediately
    if isinstance(out, dict) and out.get("is_authenticated"):
        try:
            duration = int((time.time() - start_time) * 1000)
            logger.info(
                "auth.whoami",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "is_authenticated": out.get("is_authenticated"),
                        "duration_ms": duration,
                    }
                },
            )
        except Exception as e:
            logger.warning(
                "whoami: success_log_error=true, error=%s", str(e), exc_info=True
            )
        # Set caching headers on the provided response and return dict
        try:
            response.headers["Vary"] = "Origin"
            # Prevent any intermediary/browser caching - always fresh
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        except Exception as e:
            logger.warning(
                "whoami: headers_error=true, error=%s", str(e), exc_info=True
            )
        return out  # FastAPI will serialize and include headers/cookies from response

    # Otherwise, attempt silent rotation if refresh cookie present and no access cookie
    try:
        from ..cookies import read_access_cookie, read_refresh_cookie

        access_cookie = read_access_cookie(request)
        has_refresh = bool(read_refresh_cookie(request))
        if not access_cookie and has_refresh:
            # Use the new auth_refresh module for lazy refresh
            try:
                from ..auth_refresh import perform_lazy_refresh
                from ..deps.user import get_current_user_id

                current_user_id = get_current_user_id(request=request)
                # IMPORTANT: set cookies on the actual response object so Set-Cookie is returned
                await perform_lazy_refresh(request, response, current_user_id)
            except Exception as e:
                logger.warning(
                    "whoami: lazy_refresh_response_error=true, error=%s",
                    str(e),
                    exc_info=True,
                )
    except Exception as e:
        logger.warning(
            "whoami: lazy_refresh_response_setup_error=true, error=%s",
            str(e),
            exc_info=True,
        )

    try:
        duration = int((time.time() - start_time) * 1000)
        logger.info(
            "🔍 WHOAMI_RESPONSE: Returning whoami response", extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "req_id": req_id,
                    "is_authenticated": out.get("is_authenticated", False),
                    "session_ready": out.get("session_ready", False),
                    "user_id": out.get("user_id"),
                    "source": out.get("source"),
                    "response_data": out,
                    "duration_ms": duration,
                    "timestamp": time.time()
                }
            },
        )
    except Exception as e:
        logger.warning(
            "whoami: response_log_error=true, error=%s", str(e), exc_info=True
        )

    # Set caching headers on the provided response and return dict
    try:
        response.headers["Vary"] = "Origin"
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    except Exception as e:
        logger.warning(
            "whoami: response_headers_error=true, error=%s", str(e), exc_info=True
        )
    return out


# Device sessions endpoints were moved to app.api.me for canonical shapes.


@router.get("/pats", include_in_schema=False)
async def list_pats(
    request: Request,
) -> RedirectResponse:
    """Legacy PATs endpoint - redirect to canonical route.

    This legacy endpoint should redirect to the canonical PATs management.
    """
    # Legacy route - redirect to canonical endpoint
    return RedirectResponse(url="/v1/auth/pats", status_code=308)


@router.post(
    "/pats",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {
                            "name": "CI token",
                            "scopes": ["admin:write"],
                            "exp_at": None,
                        }
                    }
                }
            }
        }
    },
)
async def create_pat(
    body: dict[str, Any], user_id: str = Depends(get_current_user_id)
) -> dict[str, Any]:
    if user_id == "anon":
        from ..http_errors import unauthorized

        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )
    name = str(body.get("name") or "")
    scopes = body.get("scopes") or []
    exp_at = body.get("exp_at")
    if not name or not isinstance(scopes, list):
        raise HTTPException(status_code=400, detail="invalid_request")
    pat_id = f"pat_{secrets.token_hex(4)}"
    token = f"pat_live_{secrets.token_urlsafe(24)}"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    await _create_pat(
        id=pat_id,
        user_id=user_id,
        name=name,
        token_hash=token_hash,
        scopes=scopes,
        exp_at=None,
    )
    return {"id": pat_id, "token": token, "scopes": scopes, "exp_at": exp_at}


@router.delete("/pats/{pat_id}", include_in_schema=False)
async def revoke_pat(
    pat_id: str,
    request: Request,
) -> dict[str, str]:
    """Legacy PAT revoke endpoint - redirect to canonical route.

    Args:
        pat_id: The PAT ID to revoke

    Returns:
        dict: Success confirmation
    """
    # Legacy route - redirect to canonical endpoint
    return RedirectResponse(url=f"/v1/auth/pats/{pat_id}", status_code=308)


def _jwt_secret() -> str:
    sec = os.getenv("JWT_SECRET")
    if not sec or sec.strip() == "":
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    # Do not automatically allow weaker secrets for test mode here; only
    # allow an explicit DEV_MODE bypass below. This avoids silently relaxing
    # checks during unit tests and keeps security checks strict by default.
    # Allow DEV_MODE to relax strength checks (explicit opt-in)
    try:
        dev_mode = str(os.getenv("DEV_MODE", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        # Only allow DEV_MODE bypass when NOT running tests. Tests should still
        # exercise the strict secret validation unless they explicitly opt-in.
        if dev_mode and not _in_test_mode():
            try:
                logging.getLogger(__name__).warning(
                    "Using weak JWT_SECRET because DEV_MODE=1 is set. Do NOT use in production."
                )
            except Exception as e:
                logger.error(
                    "jwt_secret: dev_mode_warning_error=true, error=%s",
                    str(e),
                    exc_info=True,
                )
            return sec
    except Exception as e:
        logger.error(
            "jwt_secret: configuration_error=true, error=%s", str(e), exc_info=True
        )
    # Security check: prevent use of default/placeholder secrets
    # Allow "secret" for test compatibility
    insecure_secrets = {"change-me", "default", "placeholder", "key"}
    if sec.strip().lower() == "secret":
        insecure_secrets.discard("secret")
    if sec.strip().lower() in insecure_secrets:
        raise HTTPException(status_code=500, detail="insecure_jwt_secret")
    return sec


def _key_pool_from_env() -> dict[str, str]:
    raw = os.getenv("JWT_KEYS") or os.getenv("JWT_KEY_POOL")
    if raw:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and obj:
                return {str(k): str(v) for k, v in obj.items()}
        except Exception as e:
            logger.warning(
                "jwt_secret: json_parse_error=true, error=%s", str(e), exc_info=True
            )
        try:
            items = [p.strip() for p in str(raw).split(",") if p.strip()]
            out: dict[str, str] = {}
            for it in items:
                if ":" in it:
                    kid, sec = it.split(":", 1)
                    out[kid.strip()] = sec.strip()
            if out:
                return out
        except Exception as e:
            logger.warning(
                "jwt_secret: key_value_parse_error=true, error=%s",
                str(e),
                exc_info=True,
            )
    sec = os.getenv("JWT_SECRET")
    if not sec or sec.strip() == "":
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    # Security check: prevent use of default/placeholder secrets
    # Allow "secret" during testing for test compatibility
    insecure_secrets = {"change-me", "default", "placeholder", "key"}
    if _in_test_mode() or sec.strip().lower() == "secret":
        # Allow "secret" for tests and explicit test usage
        insecure_secrets.discard("secret")
    if sec.strip().lower() in insecure_secrets:
        raise HTTPException(status_code=500, detail="insecure_jwt_secret")
    return {"k0": sec}


def _primary_kid_secret() -> tuple[str, str]:
    pool = _key_pool_from_env()
    if not pool:
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    kid, sec = next(iter(pool.items()))
    return kid, sec


def _decode_any_strict(token: str, *, leeway: int = 0) -> dict:
    pool = _key_pool_from_env()
    if not pool:
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    try:
        hdr = jwt.get_unverified_header(token)
        kid = hdr.get("kid")
    except Exception:
        kid = None
    keys = list(pool.items())
    if kid and kid in pool:
        keys = [(kid, pool[kid])] + [(k, s) for (k, s) in pool.items() if k != kid]
    elif kid and kid not in pool:
        try:
            logger.info("auth.jwt kid_not_found attempting_pool_refresh")
        except Exception as e:
            logger.warning(
                "jwt_decode: kid_not_found_log_error=true, error=%s",
                str(e),
                exc_info=True,
            )
    last_err: Exception | None = None
    for _, sec in keys:
        try:
            return jwt_decode(token, sec, algorithms=["HS256"], leeway=leeway)
        except Exception as e:
            last_err = e
            continue
    if isinstance(last_err, jwt.ExpiredSignatureError):
        raise last_err
    from ..http_errors import unauthorized

    raise unauthorized(
        message="authentication required", hint="login or include Authorization header"
    )


def _get_refresh_ttl_seconds() -> int:
    """Return refresh token TTL in seconds using consistent precedence.

    Precedence:
    1) JWT_REFRESH_TTL_SECONDS (seconds)
    2) JWT_REFRESH_EXPIRE_MINUTES (minutes → seconds)
    Default: 7 days.
    """
    try:
        v = os.getenv("JWT_REFRESH_TTL_SECONDS")
        if v is not None and str(v).strip() != "":
            return max(1, int(v))
    except Exception as e:
        logger.warning(
            "jwt_ttl: seconds_config_error=true, error=%s", str(e), exc_info=True
        )
    try:
        vmin = os.getenv("JWT_REFRESH_EXPIRE_MINUTES")
        if vmin is not None and str(vmin).strip() != "":
            return max(60, int(vmin) * 60)
    except Exception as e:
        logger.warning(
            "jwt_ttl: minutes_config_error=true, error=%s", str(e), exc_info=True
        )
    return 7 * 24 * 60 * 60


@router.get("/finish", include_in_schema=False)
@router.post("/finish", include_in_schema=False)
@public_route
async def finish_clerk_login(request: Request, response: Response):
    """Legacy finish endpoint - redirect to canonical route.

    This legacy endpoint should redirect to the canonical finish route.
    """
    # Legacy route - redirect to canonical endpoint
    return RedirectResponse(url="/v1/auth/finish", status_code=308)


# Minimal debug endpoint for Clerk callback path discovery (no auth dependency)
@router.get("/auth/clerk/finish")
@router.post("/auth/clerk/finish")
async def clerk_finish(request: Request) -> dict[str, Any]:
    try:
        logger.info(">> Clerk callback hit: %s", request.url)
        try:
            body = await request.body()
        except Exception:
            body = b""
        logger.info(">> Body: %s", body)
    except Exception as e:
        logger.warning("debug_body: log_error=true, error=%s", str(e), exc_info=True)
    # Echo minimal info so callers see something structured
    try:
        return {"status": "ok", "path": str(request.url), "length": len(body)}  # type: ignore[name-defined]
    except Exception as e:
        logger.warning(
            "clerk_finish: response_error=true, error=%s", str(e), exc_info=True
        )
        return {"status": "ok"}


# rotate_refresh_cookies function removed - replaced by auth_refresh module


@router.post(
    "/register",
    dependencies=[Depends(require_scope("auth:register"))],
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {"access_token": "jwt", "refresh_token": "jwt"}
                    }
                }
            }
        },
        400: {"description": "invalid or username_taken"},
    },
)
async def register_v1(request: Request, response: Response):
    """Create a local account and return tokens.

    Matches frontend expectation for POST /v1/register.
    - Stores credentials in the lightweight auth_users table (auth_password backend)
    - Issues access and refresh tokens
    - Sets HttpOnly cookies via centralized cookie helpers
    """
    # Import required modules
    from datetime import datetime

    from sqlalchemy.exc import IntegrityError

    from app.db.core import get_async_db
    from app.db.models import AuthUser

    from ..auth import _create_session_id
    from ..auth_refresh import _get_or_create_device_id
    from ..cookie_config import get_token_ttls
    from ..tokens import make_access, make_refresh
    from ..web.cookies import set_auth_cookies
    from .auth import _jwt_secret as _secret_fn
    from .auth_password import _pwd

    # Parse body
    try:
        body = await request.json()
        username = (body.get("username") or "").strip().lower()
        password = body.get("password") or ""
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json_payload")

    # Basic validation
    if not username or len(password.strip()) < 6:
        raise HTTPException(status_code=400, detail="invalid")

    # Register user using PostgreSQL via auth_password module
    try:
        h = _pwd.hash(password)

        user = AuthUser(
            username=username,
            email=f"{username}@local.auth",  # Generate a dummy email for username-based auth
            password_hash=h,
            name=username,  # Use username as display name
            created_at=datetime.now(UTC),
        )

        async with get_async_db() as session:
            try:
                session.add(user)
                await session.commit()
            except IntegrityError:
                raise HTTPException(status_code=400, detail="username_taken")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"registration_error: {e}")
                raise HTTPException(status_code=500, detail="registration_error")
    except Exception as e:
        logger.error(f"database_error: {e}")
        raise HTTPException(status_code=500, detail="database_error")

    # Issue tokens and set cookies (mirror /v1/login behavior)
    access_ttl, refresh_ttl = get_token_ttls()
    # Get or create device_id for token binding

    device_id = _get_or_create_device_id(request, response)

    access_token = make_access(
        {"user_id": username, "device_id": device_id}, ttl_s=access_ttl
    )

    # Create refresh with JTI
    try:
        import os as _os

        import jwt as _jwt

        int(time.time())
        jti = _jwt.api_jws.base64url_encode(_os.urandom(16)).decode()
        refresh_token = make_refresh(
            {"user_id": username, "jti": jti, "device_id": device_id}, ttl_s=refresh_ttl
        )
    except Exception:
        # Fallback minimal refresh
        jti = None
        refresh_token = make_refresh(
            {"user_id": username, "device_id": device_id}, ttl_s=refresh_ttl
        )

    # Map session id and set cookies
    try:
        payload = jwt_decode(
            access_token, _secret_fn(), algorithms=["HSHS256" if False else "HS256"]
        )  # ensure HS256
        at_jti = payload.get("jti")
        exp = payload.get("exp", time.time() + access_ttl)
        session_id = _create_session_id(at_jti, exp) if at_jti else new_session_id()

        set_auth_cookies(
            response,
            access=access_token,
            refresh=refresh_token,
            session_id=session_id,
            access_ttl=access_ttl,
            refresh_ttl=refresh_ttl,
            request=request,
        )

        # Allow refresh for this session family
        try:
            from ..deps.user import resolve_session_id
            from ..token_store import allow_refresh

            sid = resolve_session_id(request=request, user_id=username)
            if jti:
                await allow_refresh(sid, jti, ttl_seconds=refresh_ttl)
        except Exception as e:
            logger.warning(
                "register: refresh_allow_error=true, error=%s", str(e), exc_info=True
            )
    except Exception as e:
        logger.warning(
            "register: cookie_set_failed=true, error=%s", str(e), exc_info=True
        )

    # Update user metrics
    try:
        user = await get_user_async(username)
        if user:
            await user_store.ensure_user(user.id)
            await user_store.update_login_stats(user.id)
    except Exception as e:
        logger.warning(
            "register: user_metrics_error=true, error=%s", str(e), exc_info=True
        )

    return {"access_token": access_token, "refresh_token": refresh_token}


from ..auth_protection import public_route


@router.post(
    "/auth/login",
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
    username: str | None = Query(None, description="Username (query fallback)"),
):
    """Dev login scaffold.

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """

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
    # Smart minimal login: accept any non-empty username for dev; in prod plug real check
    if not username:
        raise HTTPException(status_code=400, detail="missing_username")
    # In a real app, validate password/OTP/etc. Here we mint a session for the username
    # Rate-limit login attempts: IP 5/min & 30/hour; username 10/hour
    try:
        if _is_rate_limit_enabled():
            from ..token_store import _key_login_ip, _key_login_user, incr_login_counter

            ip = request.client.host if request and request.client else "unknown"
            if await incr_login_counter(_key_login_ip(f"{ip}:m"), 60) > 5:
                raise HTTPException(status_code=429, detail="too_many_requests")
            if await incr_login_counter(_key_login_ip(f"{ip}:h"), 3600) > 30:
                raise HTTPException(status_code=429, detail="too_many_requests")
            if await incr_login_counter(_key_login_user(username), 3600) > 10:
                raise HTTPException(status_code=429, detail="too_many_requests")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "login_flow: rate_limit_error=true, error=%s", str(e), exc_info=True
        )
        raise HTTPException(status_code=500, detail="rate_limit_error")

    # Use centralized cookie configuration for sharp and consistent cookies
    from ..cookie_config import get_cookie_config, get_token_ttls

    get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()

    # Use consistent TTL from cookie config
    # Use tokens.py facade instead of direct JWT encoding
    # Get or create device_id for token binding
    from ..auth_refresh import _get_or_create_device_id
    from ..tokens import make_access

    device_id = _get_or_create_device_id(request, response)

    jwt_token = make_access(
        {"user_id": username, "device_id": device_id}, ttl_s=access_ttl
    )

    # Also issue a refresh token and mark it allowed for this session
    refresh_token = None
    session_id = None
    try:
        import jwt

        now = int(time.time())
        # Longer refresh in prod: default 7 days (604800s), allow override via env
        refresh_life = _get_refresh_ttl_seconds()
        import os as _os

        jti = jwt.api_jws.base64url_encode(_os.urandom(16)).decode()
        refresh_payload = {
            "user_id": username,
            "sub": username,
            "type": "refresh",
            "iat": now,
            "exp": now + refresh_life,
            "jti": jti,
        }
        iss = os.getenv("JWT_ISSUER")
        aud = os.getenv("JWT_AUDIENCE")
        if iss:
            refresh_payload["iss"] = iss
        if aud:
            refresh_payload["aud"] = aud
        # Use tokens.py facade instead of direct JWT encoding
        from ..tokens import make_refresh

        refresh_token = make_refresh(
            {"user_id": username, "jti": jti, "device_id": device_id},
            ttl_s=refresh_life,
        )

        # Create opaque session ID instead of using JWT
        try:
            from ..auth import _create_session_id

            payload = _decode_any(jwt_token)
            jti = payload.get("jti")
            expires_at = payload.get("exp", time.time() + access_ttl)
            if jti:
                session_id = _create_session_id(jti, expires_at)
            else:
                session_id = new_session_id()
        except Exception as e:
            logger.warning(f"Failed to create session ID: {e}")
            session_id = new_session_id()

        # Use centralized cookie functions
        from ..web.cookies import set_auth_cookies

        set_auth_cookies(
            response,
            access=jwt_token,
            refresh=refresh_token,
            session_id=session_id,
            access_ttl=access_ttl,
            refresh_ttl=refresh_ttl,
            request=request,
        )
        _append_legacy_auth_cookie_headers(
            response,
            access=jwt_token,
            refresh=refresh_token,
            session_id=session_id,
            request=request,
        )
        # Best-effort device cookie for soft device binding (1 year)
        try:
            if not request.cookies.get("did"):
                from ..cookies import set_device_cookie

                set_device_cookie(
                    response,
                    value=secrets.token_hex(16),
                    ttl=365 * 24 * 3600,
                    request=request,
                    cookie_name="did",
                )
        except Exception as e:
            logger.warning(
                "login: device_cookie_error=true, error=%s", str(e), exc_info=True
            )
        # Use centralized session ID resolution to ensure consistency
        sid = resolve_session_id(request=request, user_id=username)
        await allow_refresh(sid, jti, ttl_seconds=refresh_ttl)
    except Exception as e:
        # Best-effort; login still succeeds with access token alone
        logger.error(
            "login: cookie_setting_error=true, error=%s", str(e), exc_info=True
        )
    # Get the user's UUID for user_store operations
    user = await get_user_async(username)
    if user:
        await user_store.ensure_user(user.id)
        await user_store.update_login_stats(user.id)
    # Debug: print Set-Cookie headers sent
    try:
        if os.getenv("AUTH_DEBUG") == "1":
            log_set_cookie(response, route="/v1/auth/login", user_id=username)
    except Exception as e:
        logger.warning("login: debug_log_error=true, error=%s", str(e), exc_info=True)
    # Always return tokens in dev login to support header-auth mode and debugging.
    # In cookie mode the client may ignore these fields.
    from datetime import UTC, datetime
    return {
        "status": "ok",
        "user_id": username,
        "access_token": jwt_token,
        "refresh_token": refresh_token,
        "session_id": session_id,
        "is_authenticated": True,  # For frontend auth state synchronization
        "login_timestamp": datetime.now(UTC).isoformat(),
        "auth_source": "cookie",  # Indicates tokens set as cookies
        "session_ready": True,
    }


# Legacy login route removed - now handled by redirect in app.auth:router
@router.post("/auth/token")
async def dev_token(
    request: Request,
    username: str = Form(None),
    password: str = Form(None),
    scope: str = Form(""),
):
    """Password-style token endpoint for dev/test.

    - Disabled when DISABLE_DEV_TOKEN=1
    - Requires JWT_SECRET and enforces a minimally secure secret
    - Returns bearer token with optional scopes in payload
    """
    import os as _os

    if (_os.getenv("DISABLE_DEV_TOKEN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        from app.http_errors import forbidden

        raise forbidden(code="dev_token_disabled", message="dev token disabled")

    sec = _os.getenv("JWT_SECRET")
    if not sec or not str(sec).strip():
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    # Treat obvious placeholders/short strings as insecure for tests
    low = sec.strip().lower()
    if (
        len(sec) < 16
        or low.startswith("change")
        or low in {"default", "placeholder", "secret", "key"}
    ):
        raise HTTPException(status_code=500, detail="insecure_jwt_secret")

    if not username:
        raise HTTPException(status_code=400, detail="missing_username")

    # Issue short-lived access token using tokens facade
    try:
        from ..cookie_config import get_token_ttls
        from ..tokens import make_access

        access_ttl, _ = get_token_ttls()
        payload: dict[str, Any] = {"user_id": username}
        if scope:
            payload["scope"] = scope
        token = make_access(payload, ttl_s=access_ttl)
    except Exception as e:
        raise HTTPException(status_code=500, detail="token_issue_failed") from e

    return {"access_token": token, "token_type": "bearer"}


@router.post(
    "/auth/logout",
    responses={204: {"description": "Logout successful"}},
)
async def logout(request: Request, response: Response):
    """Logout current session family.

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """

    # Revoke refresh family bound to session id (did/sid) when possible
    try:
        from ..token_store import revoke_refresh_family

        # Use centralized session ID resolution to ensure consistency
        sid = resolve_session_id(request=request)

        # TTL: align with remaining refresh TTL when available; best-effort 7d
        await revoke_refresh_family(sid, ttl_seconds=_get_refresh_ttl_seconds())
    except Exception as e:
        # Best-effort token revocation - continue with cookie clearing
        logger.warning(
            "logout: revoke_refresh_family_error=true, error=%s", str(e), exc_info=True
        )

    # Delete session from session store
    try:
        from ..session_store import get_session_store

        # Get session ID from __session cookie
        from ..cookies import read_session_cookie

        session_id = read_session_cookie(request)
        if session_id:
            store = get_session_store()
            store.delete_session(session_id)
            logger.info(
                "auth.session_deleted",
                extra={
                    "session_id": session_id,
                },
            )
    except Exception as e:
        logger.warning(f"Failed to delete session: {e}")
        # Continue with cookie clearing even if session deletion fails

    # Clear cookies using centralized function
    try:
        from ..cookies import clear_auth_cookies, clear_device_cookie

        clear_auth_cookies(response, request)
        # Also clear device_id cookie to ensure complete logout
        clear_device_cookie(response, request, cookie_name="device_id")
        logger.info("logout.clear_cookies centralized cookies=4")  # auth + device
        # Also clear via web facade to emit per-cookie headers expected by some tests
        try:
            from ..web.cookies import clear_auth_cookies as _web_clear

            _web_clear(response, request)
        except Exception as e:
            logger.warning(
                "logout: web_clear_error=true, error=%s", str(e), exc_info=True
            )
    except Exception as e:
        # Ultimate fallback: clear cookies using centralized cookie functions
        # This ensures cookies are cleared even if cookie_config fails
        logger.warning(
            "logout: web_clear_setup_error=true, error=%s", str(e), exc_info=True
        )
        try:
            from ..cookies import clear_auth_cookies

            clear_auth_cookies(response, request)
            logger.info("logout.clear_cookies fallback cookies=3")
        except Exception as e:
            # If even the fallback fails, we can't do much more
            # The response will still be 204, indicating logout was processed
            logger.warning(
                "logout: fallback_clear_error=true, error=%s", str(e), exc_info=True
            )

    # 204 No Content per contract
    response.status_code = 204
    return response


@router.post(
    "/auth/logout_all",
    responses={204: {"description": "Logout all sessions for this family"}},
)
async def logout_all(request: Request, response: Response):
    """Revoke the refresh family for the current session and clear cookies.

    Best-effort; returns 204 even if revocation partially fails.
    """
    try:
        from ..deps.user import resolve_session_id_strict
        from ..token_store import revoke_refresh_family

        sid = resolve_session_id_strict(request=request)
        if sid:
            await revoke_refresh_family(sid, ttl_seconds=_get_refresh_ttl_seconds())
    except Exception as e:
        logger.error(
            "logout_flow: revoke_refresh_family_error=true, error=%s",
            str(e),
            exc_info=True,
        )
    # Delete session id
    try:
        from ..session_store import get_session_store
        from ..cookies import read_session_cookie

        sid = read_session_cookie(request)
        if sid:
            _delete_session_id(sid)
    except Exception as e:
        logger.warning(
            "logout: delete_session_error=true, error=%s", str(e), exc_info=True
        )
    # Clear cookies
    try:
        from ..cookies import clear_auth_cookies, clear_device_cookie

        clear_auth_cookies(response, request)
        # Also clear device_id cookie to ensure complete logout
        clear_device_cookie(response, request, cookie_name="device_id")
    except Exception as e:
        logger.error(
            "logout_flow: clear_cookies_error=true, error=%s", str(e), exc_info=True
        )
    response.status_code = 204
    return response


@router.post(
    "/auth/refresh",
    response_model=RefreshOut,
    response_model_exclude_none=True,
    responses={
        200: {
            "content": {"application/json": {"schema": {"example": {"rotated": False}}}}
        }
    },
)
async def refresh(
    request: Request, response: Response, _: None = Depends(log_request_meta)
):
    """Rotate access/refresh cookies.

    Intent: When COOKIE_SAMESITE=none, require header X-Auth-Intent: refresh.
    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """
    # Import HTTPException at function level for CSRF validation
    from fastapi import HTTPException

    # Global CSRF enforcement for mutating routes when enabled
    try:
        if os.getenv("CSRF_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}:
            from ..csrf import _extract_csrf_header as _csrf_extract

            tok, used_legacy, allowed = _csrf_extract(request)

            # Check if we're in a cross-site scenario (COOKIE_SAMESITE=none)
            is_cross_site = os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"

            if is_cross_site:
                # Cross-site CSRF validation: require intent header + additional security
                if not tok:
                    raise HTTPException(
                        status_code=400, detail="missing_csrf_cross_site"
                    )

                # For cross-site, we can't rely on same-origin cookies, so we use a different approach:
                # 1. Require the CSRF token in header
                # 2. Validate against a server-side session or use a different mechanism
                # 3. Additional validation: check if the request has proper intent headers

                # Validate intent header is present for cross-site requests
                intent = request.headers.get("x-auth-intent") or request.headers.get(
                    "X-Auth-Intent"
                )
                if str(intent or "").strip().lower() != "refresh":
                    logger.info(
                        "refresh_flow: csrf_failed=true, reason=missing_intent_header_cross_site"
                    )
                    raise HTTPException(
                        status_code=400, detail="missing_intent_header_cross_site"
                    )

                # For cross-site, we'll accept the CSRF token from header only
                # This is less secure than double-submit, but necessary for cross-site functionality
                if not tok or len(tok) < 16:  # Basic validation
                    logger.info(
                        "refresh_flow: csrf_failed=true, reason=invalid_csrf_format"
                    )
                    from app.http_errors import forbidden

                    raise forbidden(
                        code="invalid_csrf_format", message="invalid CSRF token format"
                    )

                # TODO: Consider implementing server-side CSRF token validation for cross-site requests
                # This could involve storing valid tokens in Redis/session and validating against that

            else:
                # Standard same-origin CSRF validation (double-submit pattern)
                if used_legacy and not allowed:
                    logger.info("refresh_flow: csrf_failed=true, reason=missing_csrf")
                    raise HTTPException(status_code=400, detail="missing_csrf")
                cookie = request.cookies.get("csrf_token")
                if not tok or not cookie or tok != cookie:
                    logger.info("refresh_flow: csrf_failed=true, reason=invalid_csrf")
                    raise HTTPException(status_code=400, detail="invalid_csrf")
        else:
            # When CSRF is disabled, still require intent header for cross-site requests
            if os.getenv("COOKIE_SAMESITE", "lax").lower() == "none":
                intent = request.headers.get("x-auth-intent") or request.headers.get(
                    "X-Auth-Intent"
                )
                if str(intent or "").strip().lower() != "refresh":
                    raise HTTPException(
                        status_code=400, detail="missing_intent_header_cross_site"
                    )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "refresh_flow: csrf_validation_error=true, error=%s", str(e), exc_info=True
        )
        raise HTTPException(status_code=500, detail="csrf_validation_error")

    # CSRF validation passed
    logger.info("refresh_flow: csrf_passed=true")

    # Rate-limit refresh per session id (sid) 60/min
    try:
        if _is_rate_limit_enabled():
            from ..token_store import incr_login_counter

            # Use centralized session ID resolution for rate limiting
            sid = resolve_session_id(request=request)
            # Rate-limit per family and per-IP
            ip = request.client.host if request.client else "unknown"
            fam_hits = await incr_login_counter(f"rl:refresh:fam:{sid}", 60)
            ip_hits = await incr_login_counter(f"rl:refresh:ip:{ip}", 60)
            fam_cap = 60
            ip_cap = 120
            if fam_hits > fam_cap or ip_hits > ip_cap:
                raise HTTPException(status_code=429, detail="too_many_requests")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "refresh_flow: rate_limit_error=true, error=%s", str(e), exc_info=True
        )
        raise HTTPException(status_code=500, detail="rate_limit_error")
    # Use the new robust refresh implementation
    from ..metrics_auth import (
        record_refresh_latency,
        refresh_rotation_failed,
        refresh_rotation_success,
        replay_detected,
    )

    try:
        # Optional JSON body may supply refresh_token for header-mode clients
        refresh_override: str | None = None
        try:
            body = await request.json()
            if isinstance(body, dict):
                val = body.get("refresh_token")
                if isinstance(val, str) and val:
                    refresh_override = val
        except Exception:
            refresh_override = None

        # Log incoming refresh token status
        rt_source = "cookie" if not refresh_override else "body"
        from ..cookies import read_refresh_cookie

        rt_value = refresh_override or read_refresh_cookie(request) or "missing"
        logger.info(
            "refresh_flow: incoming_rt=%s, source=%s",
            rt_value[:20] + "..." if rt_value != "missing" else "missing",
            rt_source,
        )

        t0 = time.time()

        # For refresh, we need to extract user_id from refresh token itself
        # since the access token may be expired/missing
        refresh_token = rt_value
        extracted_user_id = None

        if refresh_token and refresh_token != "missing":
            try:
                payload = _decode_any(refresh_token)
                if isinstance(payload, dict):
                    extracted_user_id = payload.get("user_id") or payload.get("sub")
            except Exception as e:
                logger.warning(
                    "refresh_decode: token_decode_error=true, error=%s",
                    str(e),
                    exc_info=True,
                )

        # Get current user ID for validation (fallback if token decode fails)
        current_user_id = (
            get_current_user_id(request=request)
            if not extracted_user_id
            else extracted_user_id
        )

        # Return 401 if no valid authentication
        if current_user_id == "anon" or not current_user_id:
            from fastapi import HTTPException

            from app.http_errors import unauthorized

            raise unauthorized(code="invalid_refresh", message="invalid refresh token")

        # Perform rotation with replay protection - use shim for test compatibility
        tokens = await rotate_refresh_cookies(request, response, current_user_id)

        if tokens:
            refresh_rotation_success()
            logger.info(
                "refresh_flow: rotated=true, user_id=%s",
                tokens.get("user_id", "unknown"),
            )
            dt = int((time.time() - t0) * 1000)
            record_refresh_latency("rotation", dt)

            # Return tokens for header-mode clients - ALWAYS include both tokens
            # Debug: print Set-Cookie headers sent on rotation
            try:
                if os.getenv("AUTH_DEBUG") == "1":
                    log_set_cookie(
                        response,
                        route="/v1/auth/refresh",
                        user_id=tokens.get("user_id"),
                    )
            except Exception as e:
                logger.warning(
                    "refresh: debug_log_error=true, error=%s", str(e), exc_info=True
                )
            # Return RefreshOut with rotated=True and access_token if available
            # Use guard to prevent empty tokens
            at = tokens.get("access_token", "") if isinstance(tokens, dict) else ""
            if at and should_rotate_access(tokens.get("user_id", "")):
                # Guard against empty tokens
                if not at or not isinstance(at, str) or len(at.strip()) == 0:
                    logger.error("Empty access token detected in rotation, raising 500")
                    raise HTTPException(
                        status_code=500, detail="token_generation_failed"
                    )
                return RefreshOut(rotated=True, access_token=at)
            else:
                return RefreshOut(rotated=True, access_token=None)
        else:
            # No rotation needed (token still valid) - but we still need to return current tokens
            refresh_rotation_success()
            logger.info("refresh_flow: rotated=false, reason=token_still_valid")
            dt = int((time.time() - t0) * 1000)
            record_refresh_latency("no_rotation", dt)

            # Always return both access_token and refresh_token, even when no rotation occurs
            # Get the current valid tokens from cookies
            from ..cookies import read_access_cookie, read_refresh_cookie

            current_access_token = read_access_cookie(request) or ""
            current_refresh_token = read_refresh_cookie(request) or ""

            # Use guard to prevent empty tokens in response
            if not should_rotate_access(current_user_id):
                # No rotation needed, return without access token
                return RefreshOut(rotated=False, access_token=None)

            # Guard against empty tokens
            if current_access_token and (
                not current_access_token
                or not isinstance(current_access_token, str)
                or len(current_access_token.strip()) == 0
            ):
                logger.error(
                    "Empty access token detected in no-rotation path, raising 500"
                )
                raise HTTPException(status_code=500, detail="token_validation_failed")

            # Also set cookies when present to avoid emitting empty Set-Cookie values
            try:
                from ..cookie_config import get_token_ttls as _ttls
                from ..web.cookies import NAMES as _CN
                from ..web.cookies import set_auth_cookies as _set_c
                from ..web.cookies import set_named_cookie as _set_named

                access_ttl, refresh_ttl = _ttls()
                sid = resolve_session_id(request=request, user_id=current_user_id)

                if current_access_token and current_refresh_token:
                    _set_c(
                        response,
                        access=current_access_token,
                        refresh=current_refresh_token,
                        session_id=sid,
                        access_ttl=access_ttl,
                        refresh_ttl=refresh_ttl,
                        request=request,
                    )
                    _append_legacy_auth_cookie_headers(
                        response,
                        access=current_access_token,
                        refresh=current_refresh_token,
                        session_id=sid,
                        request=request,
                    )
                elif current_access_token:
                    _set_c(
                        response,
                        access=current_access_token,
                        refresh=None,
                        session_id=sid,
                        access_ttl=access_ttl,
                        refresh_ttl=0,
                        request=request,
                    )
                    _append_legacy_auth_cookie_headers(
                        response,
                        access=current_access_token,
                        refresh=None,
                        session_id=sid,
                        request=request,
                    )
                elif current_refresh_token:
                    # Set only the refresh cookie without touching access/session
                    _set_named(
                        resp=response,
                        name=_CN.refresh,
                        value=current_refresh_token,
                        ttl=refresh_ttl,
                        httponly=True,
                    )
                    _append_legacy_auth_cookie_headers(
                        response,
                        access=None,
                        refresh=current_refresh_token,
                        session_id=None,
                        request=request,
                    )
            except Exception as e:
                logger.warning(
                    "refresh: cookie_set_no_rotation_error=true, error=%s",
                    str(e),
                    exc_info=True,
                )
            # Debug: print Set-Cookie headers sent when no rotation
            try:
                if os.getenv("AUTH_DEBUG") == "1":
                    log_set_cookie(
                        response, route="/v1/auth/refresh", user_id=current_user_id
                    )
            except Exception as e:
                logger.warning(
                    "refresh: debug_log_no_rotation_error=true, error=%s",
                    str(e),
                    exc_info=True,
                )

            return RefreshOut(
                rotated=False,
                access_token=current_access_token if current_access_token else None,
            )

    except HTTPException:
        # Re-raise HTTP exceptions (like 401 for replay protection)
        refresh_rotation_failed("replay_protection")
        replay_detected()
        dt = int((time.time() - t0) * 1000)
        record_refresh_latency("failed", dt)
        raise
    except Exception as e:
        # Handle other errors
        refresh_rotation_failed("unknown")
        dt = int((time.time() - t0) * 1000)
        record_refresh_latency("error", dt)
        logger.error("refresh_flow: error=%s", str(e))
        from ..http_errors import unauthorized

        raise unauthorized(
            code="refresh_error",
            message="refresh failed",
            hint="try again or re-authenticate",
        )


# OAuth2 Password flow endpoint for Swagger "Authorize" in dev


@router.get("/auth/examples")
async def token_examples():
    """Return sanitized JWT examples and common scope sets.

    These are not valid tokens; use /v1/auth/token to mint a real dev token.
    """
    return {
        "samples": {
            "header": {"alg": "HS256", "typ": "JWT"},
            "payload": {
                "user_id": "dev",
                "sub": "dev",
                "exp": 1714764000,
                "scope": "admin:write",
            },
            "jwt_example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey...<redacted>...",
        },
        "scopes": [
            "care:resident",
            "care:caregiver",
            "music:control",
            "admin:write",
        ],
        "notes": "Use /v1/auth/token with 'scopes' to mint a real token in dev.",
    }


@router.get("/mock/set_access_cookie", include_in_schema=False)
async def mock_set_access_cookie(request: Request, max_age: int = 1) -> Response:
    """Dev helper: set a short-lived access_token cookie for expiry tests.

    Only enabled outside production.
    """
    if os.getenv("ENV", "dev").strip().lower() in {"prod", "production"}:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        max_age = int(max(1, int(max_age)))
    except Exception:
        max_age = 1
    # Mint a token with requested TTL
    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import make_access

    tok = make_access({"user_id": os.getenv("DEV_USER_ID", "dev")}, ttl_s=max_age)
    resp = Response(status_code=204)

    # Create opaque session ID instead of using JWT
    try:
        from ..auth import _create_session_id

        payload = _decode_any(tok)
        jti = payload.get("jti")
        expires_at = payload.get("exp", time.time() + max_age)
        if jti:
            session_id = _create_session_id(jti, expires_at)
        else:
            session_id = new_session_id()
    except Exception as e:
        logger.warning(f"Failed to create session ID: {e}")
        session_id = new_session_id()

    # Use centralized cookie functions
    from ..web.cookies import set_auth_cookies

    # For testing, use the same token for both access and refresh
    set_auth_cookies(
        resp,
        access=tok,
        refresh=tok,
        session_id=session_id,
        access_ttl=max_age,
        refresh_ttl=max_age,
        request=request,
    )
    return resp


# Test compatibility shims for legacy test imports
async def rotate_refresh_cookies(
    request: Request, response: Response, user_id: str | None = None
) -> dict[str, Any] | None:
    """Legacy shim function for tests. Delegates to the actual refresh endpoint logic.

    This function maintains backward compatibility for tests that import
    app.api.auth.rotate_refresh_cookies.
    """
    try:
        # Import the actual refresh token rotation logic
        from ..auth_refresh import rotate_refresh_token

        # Get current user ID (use provided user_id if available)
        current_user_id = user_id or get_current_user_id(request=request)

        # Perform token rotation
        tokens = await rotate_refresh_token(current_user_id, request, response)

        if tokens:
            return {
                "access_token": tokens.get("access_token", ""),
                "refresh_token": tokens.get("refresh_token", ""),
                "user_id": tokens.get("user_id", current_user_id),
            }
        else:
            # Token still valid, no rotation needed - but always return both tokens
            from ..cookies import read_access_cookie, read_refresh_cookie

            current_access_token = read_access_cookie(request) or ""
            current_refresh_token = read_refresh_cookie(request) or ""

            return {
                "access_token": current_access_token,
                "refresh_token": current_refresh_token,
                "user_id": current_user_id,
            }

    except Exception as e:
        logger.warning("rotate_refresh_cookies shim failed: %s", e)
        return None


async def _ensure_auth(user_id: str) -> None:
    """Legacy shim function for tests. Ensures auth state for a user.

    This function maintains backward compatibility for tests that import
    app.api.auth._ensure_auth.
    """
    try:
        # Basic auth validation - could be extended with actual validation logic
        if not user_id:
            from app.http_errors import unauthorized

            raise unauthorized(code="invalid_user_id", message="invalid user ID")

        # Could add additional auth checks here if needed
        # For now, just ensure the user exists in the user store
        # Use the provider pattern to avoid circular imports
        from ..middleware.middleware_core import _user_store_provider

        if _user_store_provider is not None:
            user_store = _user_store_provider()
            await user_store.ensure_user(user_id)

    except Exception as e:
        logger.warning("_ensure_auth shim failed: %s", e)
        # Don't raise exceptions in test shim - just log and continue


from ..auth_protection import public_route

# Aliases for legacy compatibility
login_v1 = login


# DEPRECATED: Add warnings when legacy exports are accessed
class _DeprecatedAccess:
    """Wrapper to warn when deprecated exports are accessed."""

    def __init__(self, obj, name: str, message: str):
        self._obj = obj
        self._name = name
        self._message = message
        self._warned = False

    def __call__(self, *args, **kwargs):
        if not self._warned:
            logger.warning(self._message)
            self._warned = True
        return self._obj(*args, **kwargs)

    def __getattr__(self, name):
        if not self._warned:
            logger.warning(self._message)
            self._warned = True
        return getattr(self._obj, name)

    # Wrap key functions with deprecation warnings
    # Note: These are defined at the end after all functions are declared

    __all__ = [
        "router",
        "verify_pat",
        "rotate_refresh_cookies",
        "_ensure_auth",
        "login",
        "login_v1",
        "register_v1",
        "refresh",
        "logout",
        "logout_all",
        "dev_token",
        "token_examples",
        "debug_cookies",
        "debug_auth_state",
        "whoami",
        "clerk_finish",
        "mock_set_access_cookie",
        "finish_clerk_login",
    ]


# Apply deprecation wrappers for legacy re-exports
login = _DeprecatedAccess(
    login,
    "login",
    "DEPRECATED: app.api.auth.login is deprecated. Import from app.auth.endpoints.login instead.",
)

login_v1 = _DeprecatedAccess(
    login_v1,
    "login_v1",
    "DEPRECATED: app.api.auth.login_v1 is deprecated. Import from app.auth.endpoints.login instead.",
)

register_v1 = _DeprecatedAccess(
    register_v1,
    "register_v1",
    "DEPRECATED: app.api.auth.register_v1 is deprecated. Import from app.auth.endpoints.register instead.",
)

refresh = _DeprecatedAccess(
    refresh,
    "refresh",
    "DEPRECATED: app.api.auth.refresh is deprecated. Import from app.auth.endpoints.refresh instead.",
)

logout = _DeprecatedAccess(
    logout,
    "logout",
    "DEPRECATED: app.api.auth.logout is deprecated. Import from app.auth.endpoints.logout instead.",
)

logout_all = _DeprecatedAccess(
    logout_all,
    "logout_all",
    "DEPRECATED: app.api.auth.logout_all is deprecated. Import from app.auth.endpoints.logout instead.",
)

dev_token = _DeprecatedAccess(
    dev_token,
    "dev_token",
    "DEPRECATED: app.api.auth.dev_token is deprecated. Import from app.auth.endpoints.token instead.",
)

token_examples = _DeprecatedAccess(
    token_examples,
    "token_examples",
    "DEPRECATED: app.api.auth.token_examples is deprecated. Import from app.auth.endpoints.token instead.",
)

debug_cookies = _DeprecatedAccess(
    debug_cookies,
    "debug_cookies",
    "DEPRECATED: app.api.auth.debug_cookies is deprecated. Import from app.auth.endpoints.debug instead.",
)

debug_auth_state = _DeprecatedAccess(
    debug_auth_state,
    "debug_auth_state",
    "DEPRECATED: app.api.auth.debug_auth_state is deprecated. Import from app.auth.endpoints.debug instead.",
)

whoami = _DeprecatedAccess(
    whoami,
    "whoami",
    "DEPRECATED: app.api.auth.whoami is deprecated. Import from app.auth.endpoints.debug instead.",
)

clerk_finish = _DeprecatedAccess(
    clerk_finish,
    "clerk_finish",
    "DEPRECATED: app.api.auth.clerk_finish is deprecated. Import from app.auth.endpoints.debug instead.",
)

mock_set_access_cookie = _DeprecatedAccess(
    mock_set_access_cookie,
    "mock_set_access_cookie",
    "DEPRECATED: app.api.auth.mock_set_access_cookie is deprecated. Import from app.auth.endpoints.debug instead.",
)

finish_clerk_login = _DeprecatedAccess(
    finish_clerk_login,
    "finish_clerk_login",
    "DEPRECATED: app.api.auth.finish_clerk_login is deprecated. Import from app.auth.endpoints.debug instead.",
)

# Warn when router is accessed (main export)
_router = router
router = _DeprecatedAccess(
    _router,
    "router",
    "DEPRECATED: app.api.auth.router is deprecated. Import from app.auth.endpoints instead.",
)
