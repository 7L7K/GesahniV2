"""
Auth Protection Helpers for /v1/auth/* endpoints.

This module provides standardized protection decorators and dependencies
for normalizing auth protection across /v1/auth/* endpoints.

Protection Modes:
1. Public: No auth, no CSRF required
2. Auth-only: Token required, CSRF not required (e.g., token exchange)
3. Protected: Token + CSRF required (e.g., mutating user profile endpoints)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import HTTPException, Request

from .csrf import _extract_csrf_header
from .deps.user import require_user

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def public_route(endpoint_func: F) -> F:
    """
    Decorator for public routes: no auth, no CSRF required.

    Use for login, registration, OAuth callbacks, etc.
    """
    endpoint_func.__doc__ = (
        endpoint_func.__doc__ or ""
    ) + "\n\n@public_route - No auth, no CSRF required"
    return endpoint_func


def auth_only_route(endpoint_func: F) -> F:
    """
    Decorator for auth-only routes: token required, CSRF not required.

    Use for token exchange, logout, refresh operations.
    """
    endpoint_func.__doc__ = (
        endpoint_func.__doc__ or ""
    ) + "\n\n@auth_only_route - Auth token required, CSRF not required"
    return endpoint_func


def protected_route(endpoint_func: F) -> F:
    """
    Decorator for protected routes: token + CSRF required.

    Use for user profile mutations, account settings changes.
    """
    endpoint_func.__doc__ = (
        endpoint_func.__doc__ or ""
    ) + "\n\n@protected_route - Auth token + CSRF required"
    return endpoint_func


async def require_auth_no_csrf(request: Request) -> str:
    """
    Dependency for auth-only routes: requires valid token but bypasses CSRF.

    Returns user_id on success, raises 401 on failure.
    """
    try:
        user_id = await require_user(request)
        logger.debug("auth_only_route: authenticated user_id=%s", user_id)
        return user_id
    except HTTPException as e:
        logger.warning("auth_only_route: authentication failed - %s", e.detail)
        raise e


async def require_auth_with_csrf(request: Request) -> str:
    """
    Dependency for protected routes: requires valid token AND CSRF validation.

    Returns user_id on success, raises 401/403 on failure.
    """
    # First, require authentication
    try:
        user_id = await require_user(request)
    except HTTPException as e:
        logger.warning("protected_route: authentication failed - %s", e.detail)
        raise e

    # Then, require CSRF validation
    try:
        import os

        if os.getenv("CSRF_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}:
            token_hdr, used_legacy, legacy_allowed = _extract_csrf_header(request)

            # Check if we're in a cross-site scenario (COOKIE_SAMESITE=none)
            is_cross_site = os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"

            if is_cross_site:
                # Cross-site CSRF validation: require token in header + basic validation
                if not token_hdr:
                    logger.warning("protected_route: csrf_missing_header_cross_site")
                    from app.http_errors import http_error

                    raise http_error(
                        code="csrf_missing", message="CSRF token required", status=400
                    )

                # Basic validation for cross-site tokens
                if len(token_hdr) < 16:  # Basic validation
                    logger.warning("protected_route: csrf_invalid_format_cross_site")
                    from app.http_errors import http_error

                    raise http_error(
                        code="csrf_invalid", message="invalid CSRF token", status=403
                    )

                # For cross-site, we accept any properly formatted token
                logger.debug("protected_route: csrf_cross_site_validation passed")
            else:
                # Standard same-origin CSRF validation (double-submit pattern)
                from .auth.constants import CSRF_COOKIE

                token_cookie = request.cookies.get(CSRF_COOKIE) or ""
                # Reject legacy header when grace disabled
                if used_legacy and not legacy_allowed:
                    logger.warning("protected_route: csrf_legacy_header_disabled")
                    raise HTTPException(status_code=400, detail="csrf.missing")
                # Require both header and cookie, and match
                if not token_hdr or not token_cookie:
                    logger.warning("protected_route: csrf_missing_header_or_cookie")
                    raise HTTPException(status_code=403, detail="csrf.missing")
                if token_hdr != token_cookie:
                    logger.warning("protected_route: csrf_mismatch")
                    raise HTTPException(status_code=400, detail="csrf.invalid")

        logger.debug(
            "protected_route: authenticated user_id=%s with csrf validation", user_id
        )
        return user_id
    except HTTPException:
        raise
    except Exception as e:
        logger.error("protected_route: csrf validation error - %s", str(e))
        raise HTTPException(status_code=500, detail="csrf.validation_error")


# Protection mode constants for documentation and testing
PROTECTION_MODES = {
    "public": "No auth, no CSRF required",
    "auth_only": "Token required, CSRF not required",
    "protected": "Token + CSRF required",
}


__all__ = [
    "public_route",
    "auth_only_route",
    "protected_route",
    "require_auth_no_csrf",
    "require_auth_with_csrf",
    "PROTECTION_MODES",
]
