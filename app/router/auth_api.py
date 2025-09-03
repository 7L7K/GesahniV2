"""Authentication API routes for the router.

This module defines /v1/auth/* routes.
Leaf module - no imports from app/router/__init__.py.
"""
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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse

from app.auth_monitoring import record_finish_call, record_whoami_call, track_auth_event
from app.auth_store import create_pat as _create_pat
from app.auth_store import get_pat_by_hash as _get_pat_by_hash
from app.auth_store import list_pats_for_user as _list_pats_for_user
from app.auth_store import revoke_pat as _revoke_pat
from app.deps.user import get_current_user_id, require_user, resolve_session_id
from app.logging_config import req_id_var
from app.metrics import AUTH_REFRESH_OK, AUTH_REFRESH_FAIL, WHOAMI_OK, WHOAMI_FAIL
from app.security import jwt_decode
from app.token_store import (
    allow_refresh,
    claim_refresh_jti_with_retry,
    get_last_used_jti,
    has_redis,
    is_refresh_family_revoked,
    set_last_used_jti,
)
from app.user_store import user_store

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(tags=["Auth"])


# Debug dependency for auth endpoints
async def log_request_meta(request: Request):
    """Log detailed request metadata for debugging auth issues."""
    cookies = list(request.cookies.keys())
    origin = request.headers.get("origin", "none")
    referer = request.headers.get("referer", "none")
    user_agent = request.headers.get("user-agent", "none")
    content_type = request.headers.get("content-type", "none")

    logger.debug(
        "auth.request_meta",
        extra={
            "rid": req_id_var.get(),
            "cookies": cookies,
            "origin": origin,
            "referer": referer,
            "user_agent": user_agent,
            "content_type": content_type,
        },
    )


@router.get(
    "/auth/finish",
    dependencies=[Depends(log_request_meta)],
    include_in_schema=False,
)
async def auth_finish_get(
    request: Request,
    response: Response,
):
    """Handle OAuth callback via GET (legacy support)."""
    try:
        await record_finish_call(request)
    except Exception:
        pass

    # Redirect to frontend
    return RedirectResponse(
        url="/",
        status_code=302,
    )


@router.post(
    "/auth/finish",
    dependencies=[Depends(log_request_meta)],
    include_in_schema=False,
)
async def auth_finish_post(
    request: Request,
    response: Response,
):
    """Handle OAuth callback via POST."""
    try:
        await record_finish_call(request)
    except Exception:
        pass

    return JSONResponse(
        content={"status": "ok"},
        status_code=200,
    )


@router.get("/examples", include_in_schema=False)
async def auth_examples():
    """Return OAuth configuration examples for debugging."""
    return {
        "oauth_providers": ["google", "apple"],
        "note": "Use /v1/google/auth/login_url for Google OAuth",
        "deprecated": "This endpoint is for debugging only",
    }


# Placeholder implementations for other auth routes
# These would need to be implemented based on the actual requirements

@router.get("/whoami", include_in_schema=False)
async def whoami(request: Request):
    """Get current user information."""
    try:
        user_id = await get_current_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        await record_whoami_call(request)
        WHOAMI_OK.inc()

        return {
            "user_id": user_id,
            "authenticated": True,
        }
    except Exception as e:
        WHOAMI_FAIL.inc()
        logger.error("whoami.failed", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.post("/refresh", include_in_schema=False)
async def refresh_token(request: Request):
    """Refresh JWT access token."""
    try:
        # Delegate to the actual implementation in app.api.auth
        from app.api.auth import refresh
        from fastapi.responses import Response
        response = Response()
        result = await refresh(request, response)
        AUTH_REFRESH_OK.inc()
        return result
    except Exception as e:
        AUTH_REFRESH_FAIL.inc()
        logger.error("refresh.failed", exc_info=True)
        raise HTTPException(status_code=401, detail="Token refresh failed")


@router.post("/logout", include_in_schema=False)
async def logout(request: Request):
    """Log out user by clearing tokens."""
    return JSONResponse(
        content={"status": "logged_out"},
        status_code=200,
    )
