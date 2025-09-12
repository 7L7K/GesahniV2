# app/api/util.py
"""
Utility endpoints for CORS preflight, health checks, and common API utilities.

This module provides explicit OPTIONS handlers to eliminate 405/OPTIONS noise
from CORS preflight requests, ensuring smooth frontend integration.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin"])


@router.options("/csrf", include_in_schema=False)
async def csrf_options():
    """
    Explicit OPTIONS handler for /v1/csrf endpoint.

    This eliminates 405 Method Not Allowed errors from CORS preflight requests
    when frontend applications need to make requests to the CSRF endpoint.

    Returns 204 No Content - CORS middleware will add appropriate headers.
    """
    return JSONResponse({}, status_code=204)


@router.get("/csrf")
async def get_csrf(request: Request):
    """Issuer endpoint for double-submit CSRF token.

    Returns JSON {"csrf_token": "<token>"} and sets a non-HttpOnly cookie
    via the centralized cookie helper. Also stores token server-side for
    enhanced cross-site validation.
    """
    import os

    from app.csrf import _csrf_token_store, get_csrf_token
    from app.web.cookies import set_csrf_cookie

    token = await get_csrf_token()
    ttl = int(os.getenv("CSRF_TTL_SECONDS", "600"))
    resp = JSONResponse({"csrf_token": token})

    # Store token server-side for enhanced validation
    _csrf_token_store.store_token(token, ttl)

    # Set cookie using central helper
    set_csrf_cookie(resp, token=token, ttl=ttl, request=request)
    return resp


@router.options("/health", include_in_schema=False)
async def health_options():
    """
    Explicit OPTIONS handler for health endpoint.

    Ensures CORS preflight requests to health checks work properly.
    """
    return JSONResponse({}, status_code=204)


@router.options("/metrics", include_in_schema=False)
async def metrics_options():
    """
    Explicit OPTIONS handler for metrics endpoint.

    Useful for monitoring systems that need CORS support.
    """
    return JSONResponse({}, status_code=204)


@router.options("/auth/token", include_in_schema=False)
async def auth_token_options():
    """
    Explicit OPTIONS handler for token endpoint.

    Ensures OAuth flows work properly with CORS.
    """
    return JSONResponse({}, status_code=204)


@router.options("/auth/apple/start", include_in_schema=False)
async def apple_auth_start_options():
    """
    Explicit OPTIONS handler for Apple OAuth start endpoint.
    """
    return JSONResponse({}, status_code=204)


@router.options("/auth/apple/callback", include_in_schema=False)
async def apple_auth_callback_options():
    """
    Explicit OPTIONS handler for Apple OAuth callback endpoint.
    """
    return JSONResponse({}, status_code=204)


# Specific OPTIONS handler only for /v1 API endpoints
@router.options("/v1/{path:path}", include_in_schema=False)
async def v1_options_handler(path: str):
    """
    OPTIONS handler for /v1 API endpoints.

    This ensures CORS preflight requests work properly for versioned API endpoints.
    """
    logger.debug("V1 OPTIONS handler", extra={"path": path})
    return JSONResponse({}, status_code=204)


# Health check utility endpoint
@router.get("/ping", include_in_schema=False)
async def ping():
    """
    Simple ping endpoint for connectivity testing.

    Returns 200 OK with minimal response for load balancer health checks
    and connectivity testing. Not included in API schema to avoid clutter.
    """
    return {"status": "ok", "service": "api"}
