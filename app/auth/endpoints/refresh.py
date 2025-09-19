from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.auth.errors import (
    ERR_INVALID_CSRF,
    ERR_MISSING_CSRF,
    ERR_MISSING_INTENT,
    ERR_TOO_MANY,
)
from app.auth.models import RefreshOut
from app.auth.service import AuthService
from app.auth.rate_limit_utils import _is_rate_limit_enabled
from app.cookies import read_access_cookie, read_refresh_cookie
from app.deps.user import get_current_user_id, resolve_session_id

router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
logger = logging.getLogger(__name__)


async def _validate_refresh_request(request: Request) -> None:
    """Validate CSRF and rate limiting for refresh requests."""
    from app.metrics_auth import record_auth_operation, record_error_code

    # CSRF validation
    try:
        if os.getenv("CSRF_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}:
            from app.csrf import _extract_csrf_header as _csrf_extract

            tok, used_legacy, allowed = _csrf_extract(request)
            is_cross_site = os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"
            if is_cross_site:
                if not tok:
                    from app.http_errors import http_error

                    record_error_code(ERR_MISSING_CSRF, "/v1/auth/refresh", "error")
                    record_auth_operation("refresh", "csrf_missing", "/v1/auth/refresh")
                    raise http_error(
                        code=ERR_MISSING_CSRF,
                        message="Missing CSRF token for cross-site request",
                        status=400,
                    )
                intent = request.headers.get("x-auth-intent") or request.headers.get(
                    "X-Auth-Intent"
                )
                if str(intent or "").strip().lower() != "refresh":
                    from app.http_errors import http_error

                    record_error_code(ERR_MISSING_INTENT, "/v1/auth/refresh", "error")
                    record_auth_operation(
                        "refresh", "intent_missing", "/v1/auth/refresh"
                    )
                    raise http_error(
                        code=ERR_MISSING_INTENT,
                        message="Missing X-Auth-Intent: refresh header required for cross-site request",
                        status=400,
                    )
                if not tok or len(tok) < 16:
                    from app.http_errors import http_error

                    record_error_code(ERR_INVALID_CSRF, "/v1/auth/refresh", "error")
                    record_auth_operation("refresh", "csrf_invalid", "/v1/auth/refresh")
                    raise http_error(
                        code=ERR_INVALID_CSRF,
                        message="invalid CSRF token format",
                        status=403,
                    )
            else:
                if used_legacy and not allowed:
                    from app.http_errors import http_error

                    record_error_code(ERR_MISSING_CSRF, "/v1/auth/refresh", "error")
                    record_auth_operation("refresh", "csrf_missing", "/v1/auth/refresh")
                    raise http_error(
                        code=ERR_MISSING_CSRF, message="Missing CSRF token", status=400
                    )
                cookie = request.cookies.get("csrf_token")
                if not tok or not cookie or tok != cookie:
                    from app.http_errors import http_error

                    record_error_code(ERR_INVALID_CSRF, "/v1/auth/refresh", "error")
                    record_auth_operation("refresh", "csrf_invalid", "/v1/auth/refresh")
                    raise http_error(
                        code=ERR_INVALID_CSRF, message="Invalid CSRF token", status=400
                    )
        else:
            if os.getenv("COOKIE_SAMESITE", "lax").lower() == "none":
                intent = request.headers.get("x-auth-intent") or request.headers.get(
                    "X-Auth-Intent"
                )
                if str(intent or "").strip().lower() != "refresh":
                    from app.http_errors import http_error

                    record_error_code(ERR_MISSING_INTENT, "/v1/auth/refresh", "error")
                    record_auth_operation(
                        "refresh", "intent_missing", "/v1/auth/refresh"
                    )
                    raise http_error(
                        code=ERR_MISSING_INTENT,
                        message="Missing X-Auth-Intent: refresh header required for cross-site request",
                        status=400,
                    )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"csrf_validation.error: {e}")
        record_auth_operation("refresh", "csrf_validation_failed", "/v1/auth/refresh")

    logger.info("refresh_flow: csrf_passed=true")

    # Rate-limit refresh per session id (sid) 60/min
    try:
        if _is_rate_limit_enabled():
            from app.token_store import incr_login_counter

            sid = resolve_session_id(request=request)
            ip = request.client.host if request.client else "unknown"
            fam_hits = await incr_login_counter(f"rl:refresh:fam:{sid}", 60)
            ip_hits = await incr_login_counter(f"rl:refresh:ip:{ip}", 60)
            fam_cap = 60
            ip_cap = 120
            if fam_hits > fam_cap or ip_hits > ip_cap:
                from app.http_errors import http_error

                record_error_code(ERR_TOO_MANY, "/v1/auth/refresh", "warning")
                record_auth_operation("refresh", "rate_limited", "/v1/auth/refresh")
                raise http_error(
                    code=ERR_TOO_MANY, message="Rate limit exceeded", status=429
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"rate_limit.error: {e}")
        record_auth_operation("refresh", "rate_limit_error", "/v1/auth/refresh")


async def rotate_refresh_cookies(
    request: Request, response: Response, user_id: str | None = None
) -> dict[str, Any] | None:
    """Legacy shim function for tests. Delegates to the actual refresh endpoint logic.

    This function maintains backward compatibility for tests that import
    app.api.auth.rotate_refresh_cookies (now inlined here).
    """
    try:
        from app.auth_refresh import rotate_refresh_token

        current_user_id = user_id or get_current_user_id(request=request)
        tokens = await rotate_refresh_token(current_user_id, request, response)
        if tokens:
            return {
                "access_token": tokens.get("access_token", ""),
                "refresh_token": tokens.get("refresh_token", ""),
                "user_id": tokens.get("user_id", current_user_id),
            }
        else:
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


@router.post(
    "/refresh",
    response_model=RefreshOut,
    response_model_exclude_none=True,
    responses={
        200: {
            "content": {"application/json": {"schema": {"example": {"rotated": False}}}}
        }
    },
)
async def refresh(request: Request, response: Response) -> RefreshOut:
    """Rotate access/refresh cookies."""

    # Perform comprehensive CSRF and rate limiting validation
    await _validate_refresh_request(request)

    # Get refresh token from cookie or body (support both for compatibility)
    refresh_token = None

    # First try to read from cookie
    from app.cookies import read_refresh_cookie
    refresh_token = read_refresh_cookie(request)

    # If not in cookie, try to read from request body
    if not refresh_token:
        try:
            body = await request.json()
            refresh_token = body.get("refresh_token")
        except Exception:
            pass

    # Orchestrate token refresh through service layer
    result = await AuthService.refresh_tokens(request, response, refresh_token)

    return RefreshOut(**result)
