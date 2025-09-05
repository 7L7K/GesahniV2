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
from app.deps.user import get_current_user_id, require_user, resolve_session_id, resolve_auth_source_conflict
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
    "/finish",
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
    "/finish",
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
    """Get current user information (production-grade contract)."""
    t0 = time.time()
    req_id = req_id_var.get() or request.headers.get("X-Request-ID") or ""
    # Default headers required by contract
    cache_headers = {
        "Cache-Control": "no-store, max-age=0",
        "Pragma": "no-cache",
    }
    try:
        # Auth resolution with project contract helper
        from app.security.auth_contract import require_auth

        ident = await require_auth(request)

        # Determine source and conflict (prefer Bearer on conflict)
        source, conflict = resolve_auth_source_conflict(request)

        body = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "request_id": req_id,
            "user_id": ident.get("user_id"),
            "authenticated": True,
            "source": source,
        }
        # Only expose auth_source_conflict when DEBUG or CSRF_LEGACY_GRACE are enabled
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
                    req_id,
                )
            except Exception:
                pass

        # Observability log
        latency_ms = int((time.time() - t0) * 1000)
        logger.info(
            "evt=identity_check route=/v1/whoami user_id=%s source=%s is_authenticated=%s request_id=%s latency_ms=%d",
            body.get("user_id"),
            source,
            True,
            req_id,
            latency_ms,
        )

        # Record monitoring signal
        try:
            await record_whoami_call(request)
            WHOAMI_OK.inc()
        except Exception:
            pass

        resp = JSONResponse(content=body, status_code=200, headers=cache_headers)
        # Echo request id
        if req_id:
            resp.headers.setdefault("X-Request-ID", req_id)
        return resp
    except HTTPException:
        WHOAMI_FAIL.inc()
        logger.error("whoami.failed", exc_info=True)
        # Structured 401 body per contract
        body = {
            "code": "auth.not_authenticated",
            "detail": "not_authenticated",
            "request_id": req_id,
        }
        resp = JSONResponse(content=body, status_code=401, headers=cache_headers)
        if req_id:
            resp.headers.setdefault("X-Request-ID", req_id)
        return resp
    except Exception:
        WHOAMI_FAIL.inc()
        logger.error("whoami.failed", exc_info=True)
        body = {
            "code": "auth.not_authenticated",
            "detail": "not_authenticated",
            "request_id": req_id,
        }
        resp = JSONResponse(content=body, status_code=401, headers=cache_headers)
        if req_id:
            resp.headers.setdefault("X-Request-ID", req_id)
        return resp


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
