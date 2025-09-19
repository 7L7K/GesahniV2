"""whoami implementation extracted from app.api.auth."""

import logging
import os
import time
from datetime import UTC, datetime

from fastapi import Request
from fastapi.responses import JSONResponse

from app.auth.jwt_utils import _decode_any
from app.auth_monitoring import record_whoami_call, track_auth_event
from app.metrics import WHOAMI_FAIL, WHOAMI_OK


async def whoami_impl(request: Request) -> JSONResponse:
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
    logger = logging.getLogger(__name__)

    with track_auth_event("whoami", user_id="unknown"):
        t0 = time.time()
        src: str = "missing"
        token_cookie: str | None = None
        token_header: str | None = None
        clerk_token: str | None = None

        from app.logging_config import req_id_var

        logger.info(
            "whoami.start",
            extra={
                "meta": {
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
        from app.cookies import read_access_cookie

        token_cookie = read_access_cookie(request)
        logger.info(
            "whoami.cookie_check",
            extra={
                "meta": {
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
            claims = _decode_any(token_cookie)
            if not isinstance(claims, dict):
                raise ValueError("invalid claims")
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
            claims = _decode_any(token_header)
            if not isinstance(claims, dict):
                raise ValueError("invalid claims")
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
                from app.deps.clerk_auth import verify_clerk_token as _verify_clerk

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
        except Exception as e:
            logger.warning(f"whoami.metrics.error: {e}")
    except Exception as e:
        logger.warning(f"whoami.latency_tracking.error: {e}")

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
        logger.warning(f"whoami.monitoring.error: {e}")

    # For public whoami endpoint, return success even when unauthenticated
    # This allows clients to check authentication status without requiring auth
    has_any_token = bool(token_header or token_cookie or clerk_token)
    if not has_any_token or (has_any_token and not session_ready):
        # Return successful response with unauthenticated state
        from fastapi.responses import JSONResponse

        from app.logging_config import req_id_var

        body = {
            "is_authenticated": False,
            "session_ready": False,
            "user": {"id": None, "email": None},
            "source": "missing",
            "version": 1,
            "request_id": req_id_var.get(),
        }
        resp = JSONResponse(body, status_code=200)
        resp.headers.setdefault("Cache-Control", "no-store, max-age=0")
        resp.headers.setdefault("Pragma", "no-cache")
        resp.headers.setdefault("Expires", "0")
        if req_id_var.get():
            resp.headers.setdefault("X-Request-ID", req_id_var.get())
        return resp

    # Prefer Bearer when both header and cookies are present; detect conflict
    try:
        from app.deps.user import resolve_auth_source_conflict as _resolve_src

        src2, conflict = _resolve_src(request)
    except Exception as e:
        logger.warning(f"whoami.auth_source_resolution.error: {e}")
        src2, conflict = src, False
    if src2:
        src = src2

    from app.logging_config import req_id_var as _rid

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
            logger.warning(f"whoami.conflict_logging.error: {e}")

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
        logger.warning(f"whoami.observability_logging.error: {e}")

    from fastapi.responses import JSONResponse

    resp = JSONResponse(body, status_code=200)
    resp.headers.setdefault("Cache-Control", "no-store, max-age=0")
    resp.headers.setdefault("Pragma", "no-cache")
    resp.headers.setdefault("Expires", "0")
    if req_id_var.get():
        resp.headers.setdefault("X-Request-ID", req_id_var.get())
    return resp
