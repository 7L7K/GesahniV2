from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from ..deps.user import get_current_user_id, require_user, resolve_session_id
from ..security import jwt_decode

require_user_clerk = None  # Clerk removed
from fastapi.responses import JSONResponse

from ..auth_monitoring import record_finish_call, record_whoami_call, track_auth_event
from ..auth_store import create_pat as _create_pat

from ..auth_store import get_pat_by_hash as _get_pat_by_hash
from ..auth_store import get_pat_by_id as _get_pat_by_id
from ..auth_store import list_pats_for_user as _list_pats_for_user
from ..auth_store import revoke_pat as _revoke_pat
from ..metrics import AUTH_REFRESH_OK, AUTH_REFRESH_FAIL, WHOAMI_OK, WHOAMI_FAIL
from ..logging_config import req_id_var
from ..token_store import (
    allow_refresh,
    claim_refresh_jti_with_retry,
    get_last_used_jti,
    has_redis,
    is_refresh_family_revoked,
    set_last_used_jti,
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

    logger.info("🔐 AUTH REQUEST DEBUG", extra={
        "meta": {
            "path": request.url.path,
            "method": request.method,
            "origin": origin,
            "referer": referer,
            "user_agent": user_agent[:100] + "..." if user_agent and len(user_agent) > 100 else user_agent,
            "content_type": content_type,
            "cookies_present": len(cookies) > 0,
            "cookie_names": cookies,
            "cookie_count": len(cookies),
            "has_auth_header": "authorization" in [h.lower() for h in request.headers.keys()],
            "query_params": dict(request.query_params),
            "client_ip": getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
        }
    })

    return request

router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
logger = logging.getLogger(__name__)
# Auth metrics are now handled by Prometheus counters in app.metrics


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





def _in_test_mode() -> bool:
    v = lambda s: str(os.getenv(s, "")).strip().lower()
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
        # Best-effort dev fallback when Clerk isn’t configured and we’re in dev
        env = os.getenv("ENV", "dev").strip().lower()
        has_clerk = any(
            bool(os.getenv(k, "").strip())
            for k in ("CLERK_JWKS_URL", "CLERK_ISSUER", "CLERK_DOMAIN")
        )
        if env in {"dev", "development"} and not has_clerk:
            return os.getenv("DEV_USER_ID", "dev")
        # Otherwise, re-raise unauthorized
        from fastapi import (
            HTTPException as _HTTPException,
        )  # lazy to avoid import cycles

        from ..http_errors import unauthorized as _unauth

        raise _unauth(message="authentication required", hint="login or include Authorization header")


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
            "whoami.start",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "req_id": req_id_var.get(),
                    "ip": request.client.host if request.client else "unknown",
                    "user_agent": request.headers.get("User-Agent", "unknown"),
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
            "whoami.cookie_check",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "req_id": req_id_var.get(),
                    "has_access_token_cookie": bool(token_cookie),
                    "cookie_length": len(token_cookie) if token_cookie else 0,
                    "cookie_count": len(request.cookies),
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
            claims = jwt_decode(token_cookie, _jwt_secret(), algorithms=["HS256"], leeway=int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60))  # type: ignore[arg-type]
            session_ready = True
            effective_uid = (
                str(claims.get("user_id") or claims.get("sub") or "") or None
            )
            jwt_status = "ok"
            logger.info(
                "whoami.cookie_jwt_decode.success",
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
                "whoami.cookie_jwt_decode.failed",
                extra={
                    "meta": {
                        "req_id": req_id_var.get(),
                        "error": str(e),
                        "error_type": type(e).__name__,
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
            claims = jwt_decode(token_header, _jwt_secret(), algorithms=["HS256"], leeway=int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60))  # type: ignore[arg-type]
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
                    effective_uid = clerk_claims.get("user_id") or clerk_claims.get("sub")
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

    # Priority 3: Try Authorization header only if cookie authentication failed
    if not session_ready and token_header:
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
            claims = jwt_decode(token_header, _jwt_secret(), algorithms=["HS256"])  # type: ignore[arg-type]
            session_ready = True
            src = "header"
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

    # Priority 4: Try Clerk authentication if all other methods failed
    if not session_ready and clerk_token and os.getenv("CLERK_ENABLED", "0") == "1":
        try:
            logger.info(
                "whoami.clerk_verify.start",
                extra={
                    "meta": {
                    "req_id": req_id_var.get(),
                        "timestamp": time.time(),
                    }
                },
            )
            from ..deps.clerk_auth import verify_clerk_token

            claims = verify_clerk_token(clerk_token)
            session_ready = True
            src = "clerk"
            effective_uid = (
                str(claims.get("sub") or claims.get("user_id") or "") or None
            )
            jwt_status = "ok"
            # Set email in request state for Clerk authentication
            try:
                email = claims.get("email") or claims.get("email_address")
                if email:
                    request.state.email = email
            except Exception as e:
                logger.error(
                    "whoami.cookie_jwt_decode.failed",
                    extra={
                        "meta": {
                    "req_id": req_id_var.get(),
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "timestamp": time.time(),
                        }
                    },
                )
            logger.info(
                "whoami.clerk_verify.success",
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
                "whoami.clerk_verify.failed",
                extra={
                    "meta": {
                    "req_id": req_id_var.get(),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "timestamp": time.time(),
                    }
                },
            )

        # If still not ready and Clerk is enabled, check for Clerk token in Authorization header
        if not session_ready and token_header and os.getenv("CLERK_ENABLED", "0") == "1":
            try:
                logger.info(
                    "whoami.clerk_header_verify.start",
                    extra={
                        "meta": {
                    "req_id": req_id_var.get(),
                            "timestamp": time.time(),
                        }
                    },
                )
                from ..deps.clerk_auth import verify_clerk_token

                claims = verify_clerk_token(token_header)
                session_ready = True
                src = "clerk"
                effective_uid = (
                    str(claims.get("sub") or claims.get("user_id") or "") or None
                )
                jwt_status = "ok"
                # Set email in request state for Clerk authentication
                try:
                    email = claims.get("email") or claims.get("email_address")
                    if email:
                        request.state.email = email
                except Exception:
                    pass
                logger.info(
                    "whoami.clerk_header_verify.success",
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
                    "whoami.clerk_header_verify.failed",
                    extra={
                        "meta": {
                    "req_id": req_id_var.get(),
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "timestamp": time.time(),
                        }
                    },
                )

    # Canonical policy: authenticated iff a valid token was presented
    is_authenticated = bool(session_ready and effective_uid)

    logger.info(
        "whoami.result",
        extra={
            "meta": {
                    "req_id": req_id_var.get(),
                "is_authenticated": is_authenticated,
                "session_ready": session_ready,
                "source": src,
                "user_id": effective_uid,
                "jwt_status": jwt_status,
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
        except Exception:
            pass
    except Exception:
        pass

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
    except Exception:
        pass

    # Return 401 if no authentication method was attempted or all failed
    has_any_token = bool(token_header or token_cookie or clerk_token)
    if not has_any_token or (has_any_token and not session_ready):
        # Structured 401 for contract
        from fastapi.responses import JSONResponse as _JSON
        from ..logging_config import req_id_var as _rid
        body = {
            "code": "auth.not_authenticated",
            "detail": "not_authenticated",
            "request_id": _rid.get(),
        }
        resp = _JSON(body, status_code=401)
        resp.headers.setdefault("Cache-Control", "no-store, max-age=0")
        resp.headers.setdefault("Pragma", "no-cache")
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
    legacy = (os.getenv("CSRF_LEGACY_GRACE") or "").strip().lower() in {"1", "true", "yes", "on"}
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
        except Exception:
            pass

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
    except Exception:
        pass

    from fastapi.responses import JSONResponse as _JSON
    resp = _JSON(body, status_code=200)
    resp.headers.setdefault("Cache-Control", "no-store, max-age=0")
    resp.headers.setdefault("Pragma", "no-cache")
    if _rid.get():
        resp.headers.setdefault("X-Request-ID", _rid.get())
    return resp


@router.get("/whoami")
async def whoami(request: Request, _: None = Depends(log_request_meta)) -> JSONResponse:
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

    # If whoami_impl returned a Response, pass it through
    from fastapi.responses import Response as _RespType
    if isinstance(out, _RespType):  # type: ignore[arg-type]
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
                        "req_id": req_id,
                        "is_authenticated": out.get("is_authenticated"),
                        "duration_ms": duration,
                    }
                },
            )
        except Exception:
            pass
        return JSONResponse(
            content=out,
            headers={
                "Vary": "Origin",
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
            },
        )

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
                await perform_lazy_refresh(request, Response(), current_user_id)
            except Exception:
                pass  # Best effort for compatibility
    except Exception:
        pass

    try:
        duration = int((time.time() - start_time) * 1000)
        logger.info(
            "auth.whoami",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "req_id": req_id,
                    "is_authenticated": out.get("is_authenticated", False),
                    "duration_ms": duration,
                }
            },
        )
    except Exception:
        pass

    return JSONResponse(
        content=out,
        headers={
            "Vary": "Origin",
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )





# Device sessions endpoints were moved to app.api.me for canonical shapes.


@router.get("/pats")
async def list_pats(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """List all PATs for the authenticated user.

    Returns:
        list[dict]: List of PATs with id, name, scopes, created_at, revoked_at (no tokens)
    """
    if user_id == "anon":
        from ..http_errors import unauthorized

        raise unauthorized(message="authentication required", hint="login or include Authorization header")
    return await _list_pats_for_user(user_id)


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

        raise unauthorized(message="authentication required", hint="login or include Authorization header")
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


@router.delete("/pats/{pat_id}")
async def revoke_pat(
    pat_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    """Revoke a PAT by setting revoked_at timestamp.

    Args:
        pat_id: The PAT ID to revoke

    Returns:
        dict: Success confirmation
    """
    if user_id == "anon":
        from ..http_errors import unauthorized

        raise unauthorized(message="authentication required", hint="login or include Authorization header")

    # Check if PAT exists and belongs to user
    pat = await _get_pat_by_id(pat_id)
    if not pat:
        raise HTTPException(status_code=404, detail="PAT not found")
    if pat["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Revoke the PAT
    await _revoke_pat(pat_id)

    return {"status": "revoked", "id": pat_id}


def _jwt_secret() -> str:
    sec = os.getenv("JWT_SECRET")
    if not sec or sec.strip() == "":
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    # Do not automatically allow weaker secrets for test mode here; only
    # allow an explicit DEV_MODE bypass below. This avoids silently relaxing
    # checks during unit tests and keeps security checks strict by default.
    # Allow DEV_MODE to relax strength checks (explicit opt-in)
    try:
        dev_mode = str(os.getenv("DEV_MODE", "0")).strip().lower() in {"1", "true", "yes", "on"}
        # Only allow DEV_MODE bypass when NOT running tests. Tests should still
        # exercise the strict secret validation unless they explicitly opt-in.
        if dev_mode and not _in_test_mode():
            try:
                logging.getLogger(__name__).warning(
                    "Using weak JWT_SECRET because DEV_MODE=1 is set. Do NOT use in production."
                )
            except Exception:
                pass
            return sec
    except Exception:
        pass
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
        except Exception:
            pass
        try:
            items = [p.strip() for p in str(raw).split(",") if p.strip()]
            out: dict[str, str] = {}
            for it in items:
                if ":" in it:
                    kid, sec = it.split(":", 1)
                    out[kid.strip()] = sec.strip()
            if out:
                return out
        except Exception:
            pass
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


def _decode_any(token: str, *, leeway: int = 0) -> dict:
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
        except Exception:
            pass
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

    raise unauthorized(message="authentication required", hint="login or include Authorization header")


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
    except Exception:
        pass
    try:
        vmin = os.getenv("JWT_REFRESH_EXPIRE_MINUTES")
        if vmin is not None and str(vmin).strip() != "":
            return max(60, int(vmin) * 60)
    except Exception:
        pass
    return 7 * 24 * 60 * 60





@router.get("/finish")
@router.post("/finish")
async def finish_clerk_login(
    request: Request, response: Response, user_id: str = Depends(_require_user_or_dev)
):
    """Set auth cookies and finish login. Idempotent: safe to call multiple times.

    Locked contract: Always returns 204 for POST, 302 for GET.
    CSRF: Required for POST when CSRF_ENABLED=1 via X-CSRF-Token matching csrf_token cookie.
    """
    with track_auth_event("finish", user_id=user_id):
        # Keep ultra-fast: no body reads, no remote calls beyond local JWT mint
        t0 = time.time()
    """Bridge Clerk session → app cookies, then redirect to app.

    Responsibilities:
    - Verify Clerk session via require_user (server-side)
    - Mint app access + refresh tokens
    - Set them as HttpOnly cookies on same origin
    - Redirect to the requested app route (default "/")
    - Idempotent: safe to call multiple times
    """
    # TTLs: defaults suitable for dev (access: 30 min; refresh: 7 days)
    # Use centralized TTL from tokens.py
    from ..tokens import get_default_access_ttl

    token_lifetime = get_default_access_ttl()
    refresh_life = _get_refresh_ttl_seconds()

    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import make_access

    access_token = make_access({"user_id": user_id}, ttl_s=token_lifetime)

    # Issue refresh token scoped to session family
    import os as _os

    import jwt as pyjwt

    # Get current time and JWT configuration
    now = datetime.now(UTC)
    iss = os.getenv("JWT_ISS")
    aud = os.getenv("JWT_AUD")

    jti = pyjwt.api_jws.base64url_encode(_os.urandom(16)).decode()
    refresh_payload = {
        "user_id": user_id,
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(seconds=refresh_life),
        "jti": jti,
        "scopes": ["care:resident", "music:control"],
    }
    if iss:
        refresh_payload["iss"] = iss
    if aud:
        refresh_payload["aud"] = aud
    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import make_refresh

    refresh_token = make_refresh({"user_id": user_id, "jti": jti}, ttl_s=refresh_life)

    # Use centralized cookie configuration for sharp and consistent cookies
    from ..cookie_config import get_cookie_config, get_token_ttls

    cookie_config = get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()

    # Build safe redirect target using centralized helper
    from ..url_helpers import sanitize_redirect_path

    next_path = sanitize_redirect_path(request.query_params.get("next"), "/")

    # Classify finisher reason for logs
    reason = "normal_login"
    try:
        if os.getenv("COOKIE_SAMESITE", "lax").lower() == "none":
            reason = "cross_site"
    except Exception:
        pass
    # SPA Style: POST returns 204 with Set-Cookie, no redirect
    # Frontend handles navigation via router.push() after successful POST
    method = str(getattr(request, "method", "")).upper()
    if method == "POST":
        # When SameSite=None (cross-site), require explicit intent header even for finisher POST
        try:
            if os.getenv("COOKIE_SAMESITE", "lax").lower() == "none":
                intent = request.headers.get("x-auth-intent") or request.headers.get(
                    "X-Auth-Intent"
                )
                if str(intent or "").strip().lower() != "refresh":
                    from ..http_errors import unauthorized

                    raise unauthorized(code="missing_intent_header", message="missing intent header", hint="include X-Auth-Intent: refresh")
        except HTTPException:
            raise
        except Exception:
            pass
        # Enforce CSRF for POST in cookie-auth flows when globally enabled
        try:
            from ..csrf import _extract_csrf_header as _csrf_extract

            if os.getenv("CSRF_ENABLED", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                tok, used_legacy, allowed = _csrf_extract(request)
                if used_legacy and not allowed:
                    raise HTTPException(status_code=400, detail="missing_csrf")
                cookie = request.cookies.get("csrf_token")
                if not tok or not cookie or tok != cookie:
                    raise HTTPException(status_code=400, detail="invalid_csrf")
        except HTTPException:
            raise
        except Exception:
            pass

        # Idempotent: Check if we already have valid cookies for this user
        # If so, just return 204 without setting new cookies
        try:
            from ..web.cookies import NAMES
            existing_access = request.cookies.get(NAMES.access)
            if existing_access:
                try:
                    claims = jwt_decode(
                        existing_access, _jwt_secret(), algorithms=["HS256"]
                    )
                    existing_user_id = str(
                        claims.get("user_id") or claims.get("sub") or ""
                    )
                    if existing_user_id == user_id:
                        # Valid cookies already exist for this user, return 204
                        try:
                            dt = int((time.time() - t0) * 1000)
                            logger.info(
                                "auth.finish t_total=%dms set_cookie=false reason=idempotent_skip",
                                dt,
                                extra={
                                    "meta": {
                    "req_id": req_id_var.get(),
                                        "duration_ms": dt,
                                        "reason": "idempotent_skip",
                                    }
                                },
                            )
                        except Exception:
                            pass

                        # Record finish call for monitoring
                        try:
                            record_finish_call(
                                status="success",
                                method="POST",
                                reason="idempotent_skip",
                                user_id=user_id,
                                set_cookie=False,
                            )
                        except Exception:
                            pass

                        return Response(status_code=204)
                except Exception:
                    # Invalid existing token, proceed with setting new ones
                    pass
        except Exception:
            # Error checking existing cookies, proceed with setting new ones
            pass

        from fastapi import Response as _Resp  # type: ignore

        resp = _Resp(status_code=204)

        # Create opaque session ID instead of using JWT
        try:
            from ..auth import _create_session_id

            payload = jwt_decode(access_token, _jwt_secret(), algorithms=["HS256"])
            jti = payload.get("jti")
            expires_at = payload.get("exp", time.time() + access_ttl)
            if jti:
                session_id = _create_session_id(jti, expires_at)
            else:
                session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
        except Exception as e:
            logger.warning(f"Failed to create session ID: {e}")
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

        # Use centralized cookie functions
        from ..web.cookies import set_auth_cookies

        set_auth_cookies(
            resp,
            access=access_token,
            refresh=refresh_token,
            session_id=session_id,
            access_ttl=access_ttl,
            refresh_ttl=refresh_ttl,
            request=request,
        )
        # One-liner timing log for finisher
        try:
            dt = int((time.time() - t0) * 1000)
            logger.info(
                "auth.finish t_total=%dms set_cookie=true reason=%s cookies=3",
                dt,
                reason,
                extra={"meta": {
                    "req_id": req_id_var.get(),"duration_ms": dt, "reason": reason}},
            )
        except Exception:
            pass

        # Record finish call for monitoring
        try:
            record_finish_call(
                status="success",
                method="POST",
                reason=reason,
                user_id=user_id,
                set_cookie=True,
            )
        except Exception:
            pass

        return resp
    # Legacy GET: redirect to next with cookies attached (fallback for direct browser navigation)
    # Note: SPA should use POST /v1/auth/finish for consistent behavior
    resp = RedirectResponse(url=next_path, status_code=302)

    # Create opaque session ID instead of using JWT
    try:
        from ..auth import _create_session_id

        payload = jwt_decode(access_token, _jwt_secret(), algorithms=["HS256"])
        jti = payload.get("jti")
        expires_at = payload.get("exp", time.time() + access_ttl)
        if jti:
            session_id = _create_session_id(jti, expires_at)
        else:
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
    except Exception as e:
        logger.warning(f"Failed to create session ID: {e}")
        session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

    # Use centralized cookie functions
    from ..web.cookies import set_auth_cookies

    set_auth_cookies(
        resp,
        access=access_token,
        refresh=refresh_token,
        session_id=session_id,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=request,
    )
    try:
        dt = int((time.time() - t0) * 1000)
        logger.info(
            "auth.finish t_total=%dms set_cookie=true reason=%s cookies=3",
            dt,
            reason,
            extra={"meta": {
                    "req_id": req_id_var.get(),"duration_ms": dt, "reason": reason}},
        )
    except Exception:
        pass

    # Record finish call for monitoring
    try:
        record_finish_call(
            status="success",
            method="GET",
            reason=reason,
            user_id=user_id,
            set_cookie=True,
        )
    except Exception:
        pass

    return resp


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
    except Exception:
        pass
    # Echo minimal info so callers see something structured
    try:
        return {"status": "ok", "path": str(request.url), "length": len(body)}  # type: ignore[name-defined]
    except Exception:
        return {"status": "ok"}


# rotate_refresh_cookies function removed - replaced by auth_refresh module


@router.post(
    "/register",
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {"example": {"access_token": "jwt", "refresh_token": "jwt"}}
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

    # Ensure table and insert user using the same store as /auth/register_pw
    try:
        from .auth_password import _pwd, _db_path, _ensure  # type: ignore
        import aiosqlite

        await _ensure()
        h = _pwd.hash(password)
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "INSERT INTO auth_users(username, password_hash) VALUES(?, ?)",
                (username, h),
            )
            await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="username_taken")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"registration_error: {e}")
        raise HTTPException(status_code=500, detail="registration_error")

    # Issue tokens and set cookies (mirror /v1/login behavior)
    from ..cookie_config import get_token_ttls
    from ..tokens import make_access, make_refresh

    access_ttl, refresh_ttl = get_token_ttls()
    access_token = make_access({"user_id": username}, ttl_s=access_ttl)

    # Create refresh with JTI
    try:
        import os as _os
        import jwt as _jwt
        now = int(time.time())
        jti = _jwt.api_jws.base64url_encode(_os.urandom(16)).decode()
        refresh_token = make_refresh({"user_id": username, "jti": jti}, ttl_s=refresh_ttl)
    except Exception:
        # Fallback minimal refresh
        jti = None
        refresh_token = make_refresh({"user_id": username}, ttl_s=refresh_ttl)

    # Map session id and set cookies
    try:
        from ..web.cookies import set_auth_cookies
        from ..auth import _create_session_id
        from .auth import _jwt_secret as _secret_fn  # dynamic secret

        payload = jwt_decode(access_token, _secret_fn(), algorithms=["HSHS256" if False else "HS256"])  # ensure HS256
        at_jti = payload.get("jti")
        exp = payload.get("exp", time.time() + access_ttl)
        session_id = _create_session_id(at_jti, exp) if at_jti else f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

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
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"register.cookie_set_failed: {e}")

    # Update user metrics
    try:
        await user_store.ensure_user(username)
        await user_store.increment_login(username)
    except Exception:
        pass

    return {"access_token": access_token, "refresh_token": refresh_token}

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
async def login(
    request: Request,
    response: Response,
    username: str = Query(..., description="Username for login"),
):
    """Dev login scaffold.

    CSRF: Required when CSRF_ENABLED=1 via X-CSRF-Token + csrf_token cookie.
    """

    # Smart minimal login: accept any non-empty username for dev; in prod plug real check
    if not username:
        raise HTTPException(status_code=400, detail="missing_username")
    # In a real app, validate password/OTP/etc. Here we mint a session for the username
    # Rate-limit login attempts: IP 5/min & 30/hour; username 10/hour
    try:
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
    except Exception:
        pass

    # Use centralized cookie configuration for sharp and consistent cookies
    from ..cookie_config import get_cookie_config, get_token_ttls

    cookie_config = get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()

    # Use consistent TTL from cookie config
    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import make_access

    jwt_token = make_access({"user_id": username}, ttl_s=access_ttl)

    # Also issue a refresh token and mark it allowed for this session
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
            {"user_id": username, "jti": jti}, ttl_s=refresh_life
        )

        # Create opaque session ID instead of using JWT
        try:
            from ..auth import _create_session_id

            payload = jwt_decode(jwt_token, _jwt_secret(), algorithms=["HS256"])
            jti = payload.get("jti")
            expires_at = payload.get("exp", time.time() + access_ttl)
            if jti:
                session_id = _create_session_id(jti, expires_at)
            else:
                session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
        except Exception as e:
            logger.warning(f"Failed to create session ID: {e}")
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

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
        except Exception:
            pass
        # Use centralized session ID resolution to ensure consistency
        sid = resolve_session_id(request=request, user_id=username)
        await allow_refresh(sid, jti, ttl_seconds=refresh_ttl)
    except Exception as e:
        # Best-effort; login still succeeds with access token alone
        logger.error(f"Exception in login cookie setting: {e}")
    await user_store.ensure_user(username)
    await user_store.increment_login(username)
    return {"status": "ok", "user_id": username}


@router.post(
    "/login",
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {"example": {"access_token": "jwt_token", "refresh_token": "refresh_jwt"}}
                }
            }
        }
    },
)
async def login_v1(
    request: Request,
    response: Response,
):
    """Main login endpoint for frontend - accepts JSON payload with username/password.

    Returns access_token and refresh_token for header-mode authentication.
    """
    # Debug logging for login endpoint
    cookies = list(request.cookies.keys())
    origin = request.headers.get("origin", "none")
    referer = request.headers.get("referer", "none")
    user_agent = request.headers.get("user-agent", "none")
    content_type = request.headers.get("content-type", "none")

    logger.info("🔐 AUTH REQUEST DEBUG", extra={
        "meta": {
            "path": request.url.path,
            "method": request.method,
            "origin": origin,
            "referer": referer,
            "user_agent": user_agent[:100] + "..." if user_agent and len(user_agent) > 100 else user_agent,
            "content_type": content_type,
            "cookies_present": len(cookies) > 0,
            "cookie_names": cookies,
            "cookie_count": len(cookies),
            "has_auth_header": "authorization" in [h.lower() for h in request.headers.keys()],
            "query_params": dict(request.query_params),
            "client_ip": getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
        }
    })

    try:
        body = await request.json()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json_payload")

    # Basic validation
    if not username:
        raise HTTPException(status_code=400, detail="missing_username")
    if not password:
        raise HTTPException(status_code=400, detail="missing_password")

    # Apply exponential backoff before authentication to prevent timing attacks
    import asyncio
    import random
    from ..auth import _should_apply_backoff, _backoff_start_ms, _backoff_max_ms

    user_key = f"user:{username.lower()}"
    if _should_apply_backoff(user_key):
        delay_ms = random.randint(_backoff_start_ms(), _backoff_max_ms())
        logger.info(
            "auth.login_applying_backoff",
            extra={
                "meta": {
                    "username": username.lower(),
                    "ip": getattr(request.client, 'host', 'unknown') if request.client else 'unknown',
                    "delay_ms": delay_ms,
                }
            },
        )
        await asyncio.sleep(delay_ms / 1000.0)

    # Validate credentials against users database
    try:
        from ..api.auth_password import _pwd, _db_path
        import aiosqlite

        async with aiosqlite.connect(_db_path()) as db:
            async with db.execute(
                "SELECT password_hash FROM auth_users WHERE username=?", (username.lower(),)
            ) as cur:
                row = await cur.fetchone()

        if not row:
            from ..auth import _record_attempt
            _record_attempt(user_key, success=False)
            from ..http_errors import unauthorized

            raise unauthorized(code="invalid_credentials", message="invalid credentials", hint="check username/password")

        if not _pwd.verify(password, row[0]):
            from ..auth import _record_attempt
            _record_attempt(user_key, success=False)
            from ..http_errors import unauthorized

            raise unauthorized(code="invalid_credentials", message="invalid credentials", hint="check username/password")

        # Record successful login
        from ..auth import _record_attempt
        _record_attempt(user_key, success=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating credentials: {e}")
        raise HTTPException(status_code=500, detail="authentication_error")

    # Rate-limit login attempts
    try:
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
    except Exception:
        pass

    # Use centralized cookie configuration for sharp and consistent cookies
    from ..cookie_config import get_cookie_config, get_token_ttls

    cookie_config = get_cookie_config(request)
    access_ttl, refresh_ttl = get_token_ttls()

    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import make_access

    jwt_token = make_access({"user_id": username}, ttl_s=access_ttl)

    # Also issue a refresh token and mark it allowed for this session
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
            {"user_id": username, "jti": jti}, ttl_s=refresh_life
        )

        # Create opaque session ID instead of using JWT
        try:
            from ..auth import _create_session_id

            payload = jwt_decode(jwt_token, _jwt_secret(), algorithms=["HS256"])
            jti = payload.get("jti")
            expires_at = payload.get("exp", time.time() + access_ttl)
            if jti:
                session_id = _create_session_id(jti, expires_at)
            else:
                session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
        except Exception as e:
            logger.warning(f"Failed to create session ID: {e}")
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

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
        # Best-effort device cookie for soft device binding (1 year)
        try:
            if not request.cookies.get("did"):
                from ..cookies import set_device_cookie
                import secrets as _secrets

                set_device_cookie(
                    response,
                    value=_secrets.token_hex(16),
                    ttl=365 * 24 * 3600,
                    request=request,
                    cookie_name="did",
                )
        except Exception:
            pass
        # Use centralized session ID resolution to ensure consistency
        sid = resolve_session_id(request=request, user_id=username)
        await allow_refresh(sid, jti, ttl_seconds=refresh_ttl)
    except Exception as e:
        # Best-effort; login still succeeds with access token alone
        logger.error(f"Exception in login cookie setting: {e}")

    await user_store.ensure_user(username)
    await user_store.increment_login(username)

    # Return tokens for header-mode authentication (what frontend expects)
    return {"access_token": jwt_token, "refresh_token": refresh_token}


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
    except Exception:
        # Best-effort token revocation - continue with cookie clearing
        pass

    # Delete session from session store
    try:
        from ..auth import _delete_session_id

        # Get session ID from __session cookie
        from ..cookies import read_session_cookie
        session_id = read_session_cookie(request)
        if session_id:
            _delete_session_id(session_id)
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
        from ..cookies import clear_auth_cookies

        clear_auth_cookies(response, request)
        logger.info("logout.clear_cookies centralized cookies=3")
    except Exception:
        # Ultimate fallback: clear cookies using centralized cookie functions
        # This ensures cookies are cleared even if cookie_config fails
        try:
            from ..cookies import clear_auth_cookies

            clear_auth_cookies(response, request)
            logger.info("logout.clear_cookies fallback cookies=3")
        except Exception:
            # If even the fallback fails, we can't do much more
            # The response will still be 204, indicating logout was processed
            pass

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
        from ..token_store import revoke_refresh_family
        from ..deps.user import resolve_session_id_strict

        sid = resolve_session_id_strict(request=request)
        if sid:
            await revoke_refresh_family(sid, ttl_seconds=_get_refresh_ttl_seconds())
    except Exception:
        pass
    # Delete session id
    try:
        from ..auth import _delete_session_id

        from ..cookies import read_session_cookie
        sid = read_session_cookie(request)
        if sid:
            _delete_session_id(sid)
    except Exception:
        pass
    # Clear cookies
    try:
        from ..cookies import clear_auth_cookies

        clear_auth_cookies(response, request)
    except Exception:
        pass
    response.status_code = 204
    return response


@router.post(
    "/auth/refresh",
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
async def refresh(request: Request, response: Response, _: None = Depends(log_request_meta)):
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
                    logger.info("refresh_flow: csrf_failed=true, reason=missing_intent_header_cross_site")
                    raise HTTPException(
                        status_code=400, detail="missing_intent_header_cross_site"
                    )

                # For cross-site, we'll accept the CSRF token from header only
                # This is less secure than double-submit, but necessary for cross-site functionality
                if not tok or len(tok) < 16:  # Basic validation
                    logger.info("refresh_flow: csrf_failed=true, reason=invalid_csrf_format")
                    raise HTTPException(status_code=403, detail="invalid_csrf_format")

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
                    raise HTTPException(status_code=400, detail="missing_intent_header_cross_site")
    except HTTPException:
        raise
    except Exception:
        pass

    # CSRF validation passed
    logger.info("refresh_flow: csrf_passed=true")

    # Rate-limit refresh per session id (sid) 60/min
    try:
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
    except Exception:
        pass
    # Use the new robust refresh implementation
    from ..auth_refresh import rotate_refresh_token
    from ..metrics_auth import (
        record_refresh_latency,
        refresh_rotation_success,
        refresh_rotation_failed,
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
        logger.info("refresh_flow: incoming_rt=%s, source=%s", rt_value[:20] + "..." if rt_value != "missing" else "missing", rt_source)

        t0 = time.time()

        # For refresh, we need to extract user_id from refresh token itself
        # since the access token may be expired/missing
        refresh_token = rt_value
        extracted_user_id = None

        if refresh_token and refresh_token != "missing":
            try:
                # Try to decode the refresh token to get user_id
                import jwt
                from ..tokens import SECRET_KEY, ALGORITHM
                payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
                extracted_user_id = payload.get("user_id") or payload.get("sub")
            except Exception:
                # If we can't decode the token, fall back to current user
                pass

        # Get current user ID for validation (fallback if token decode fails)
        current_user_id = get_current_user_id(request=request) if not extracted_user_id else extracted_user_id

        # Return 401 if no valid authentication
        if current_user_id == "anon" or not current_user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="invalid_refresh")

        # Perform rotation with replay protection - use shim for test compatibility
        tokens = await rotate_refresh_cookies(request, response, current_user_id)

        if tokens:
            refresh_rotation_success()
            logger.info("refresh_flow: rotated=true, user_id=%s", tokens.get("user_id", "unknown"))
            dt = int((time.time() - t0) * 1000)
            record_refresh_latency("rotation", dt)

            # Return tokens for header-mode clients - ALWAYS include both tokens
            body: dict[str, Any] = {"status": "ok", "user_id": tokens.get("user_id", "anon")}
            if isinstance(tokens, dict):
                body["access_token"] = tokens.get("access_token", "")
                body["refresh_token"] = tokens.get("refresh_token", "")
            return body
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

            return {
                "status": "ok",
                "user_id": current_user_id,
                "access_token": current_access_token,
                "refresh_token": current_refresh_token
            }

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
        raise unauthorized(code="refresh_error", message="refresh failed", hint="try again or re-authenticate")


# OAuth2 Password flow endpoint for Swagger "Authorize" in dev
@router.post(
    "/auth/token",
    include_in_schema=True,
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {"access_token": "<jwt>", "token_type": "bearer"}
                    }
                }
            }
        }
    },
)
async def issue_token(request: Request):
    # Gate for production environments
    if os.getenv("DISABLE_DEV_TOKEN", "0").lower() in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=403, detail="disabled")
    # Parse form payload manually to avoid 422 when disabled
    username = "dev"
    scopes: list[str] = []
    try:
        form = await request.form()
        username = (str(form.get("username") or "dev").strip()) or "dev"
        raw_scope = form.get("scope") or ""
        scopes = [s.strip() for s in str(raw_scope).split() if s.strip()]
    except Exception:
        pass
    # Use centralized TTL from tokens.py
    from ..tokens import get_default_access_ttl

    token_lifetime = get_default_access_ttl()
    now = int(time.time())
    # scopes already set above
    payload = {
        "user_id": username,
        "sub": username,
        "iat": now,
        "exp": now + token_lifetime,
    }
    if scopes:
        payload["scope"] = " ".join(sorted(set(scopes)))
    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import make_access

    claims = {"user_id": username}
    if scopes:
        claims["scopes"] = scopes
    token = make_access(claims, ttl_s=token_lifetime)
    return {"access_token": token, "token_type": "bearer"}


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

        payload = jwt_decode(tok, _jwt_secret(), algorithms=["HS256"])
        jti = payload.get("jti")
        expires_at = payload.get("exp", time.time() + max_age)
        if jti:
            session_id = _create_session_id(jti, expires_at)
        else:
            session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
    except Exception as e:
        logger.warning(f"Failed to create session ID: {e}")
        session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

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
async def rotate_refresh_cookies(request: Request, response: Response, user_id: str | None = None) -> dict[str, Any] | None:
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
                "user_id": current_user_id
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
            raise HTTPException(status_code=401, detail="invalid_user_id")

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


__all__ = ["router", "verify_pat", "rotate_refresh_cookies", "_ensure_auth"]
