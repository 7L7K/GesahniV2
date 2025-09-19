from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.auth_protection import auth_only_route
from app.deps.scopes import require_admin
from app.deps.user import get_current_user_id
from app.sessions_store import sessions_store
from app.tokens import remaining_ttl

router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
logger = logging.getLogger(__name__)


def _clear_site_data_enabled() -> bool:
    try:
        from app.settings import AUTH_ENABLE_CLEAR_SITE_DATA

        return bool(AUTH_ENABLE_CLEAR_SITE_DATA)
    except Exception:
        return os.getenv("AUTH_ENABLE_CLEAR_SITE_DATA", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }


def _finalize_logout_response(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    try:
        del response.headers["ETag"]
    except KeyError:
        pass
    if _clear_site_data_enabled():
        response.headers["Clear-Site-Data"] = '"cookies"'
    response.status_code = 204
    return response


@router.post(
    "/logout",
    responses={204: {"description": "Logout successful"}},
)
@auth_only_route
async def logout(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    """Logout user and clear all session data."""

    # Extract client information for security logging
    client_ip = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
    user_agent = request.headers.get("User-Agent", "unknown")
    origin = request.headers.get("Origin", "unknown")

    logger.info(f"🚪 LOGOUT_STEP_1: Starting logout for user '{user_id}'")
    
    from app.auth.service import AuthService

    logger.info(f"🚪 LOGOUT_STEP_2: Calling AuthService.logout_user for user '{user_id}'")
    await AuthService.logout_user(request, response, user_id)
    logger.info(f"🚪 LOGOUT_STEP_3: AuthService.logout_user completed for user '{user_id}'")

    logger.info(f"🚪 LOGOUT_SUCCESS: Logout completed for user '{user_id}' - returning 204")

    # Security event logging for successful logout
    logger.info("🚪 SECURITY_LOGOUT_SUCCESS", extra={
        "event_type": "logout_success",
        "user_id": user_id,
        "client_ip": client_ip,
        "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
        "origin": origin,
        "timestamp": __import__('time').time(),
    })

    return _finalize_logout_response(response)


@router.post(
    "/logout_all",
    responses={204: {"description": "Logout all sessions for this family"}},
)
@auth_only_route
async def logout_all(
    request: Request, response: Response, user_id: str = Depends(get_current_user_id)
):
    """Logout from all sessions in this family."""

    # Extract client information for security logging
    client_ip = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
    user_agent = request.headers.get("User-Agent", "unknown")
    origin = request.headers.get("Origin", "unknown")

    from app.auth.service import AuthService

    logger.info(f"🚪 LOGOUT_ALL_STEP_1: Starting logout_all for user '{user_id}'")
    await AuthService.logout_all_sessions(request, response, user_id)
    logger.info(f"🚪 LOGOUT_ALL_SUCCESS: Logout_all completed for user '{user_id}' - returning 204")

    # Security event logging for successful logout_all
    logger.info("🚪 SECURITY_LOGOUT_ALL_SUCCESS", extra={
        "event_type": "logout_all_success",
        "user_id": user_id,
        "client_ip": client_ip,
        "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
        "origin": origin,
        "timestamp": __import__('time').time(),
    })

    return _finalize_logout_response(response)


class RevokeReq(BaseModel):
    """Request model for revoke endpoint."""
    sid: str | None = None
    user_id: str | None = None
    jti: str | None = None


@router.post(
    "/revoke",
    status_code=204,
    responses={204: {"description": "Revocation successful"}},
)
async def revoke(
    req: RevokeReq,
    admin_scope: str = Depends(require_admin()),
):
    """Revoke sessions or tokens. Idempotent operation that always returns 204.

    Can revoke by:
    - sid: Revoke specific session
    - user_id: Revoke all sessions for user
    - jti: Blacklist specific JWT token
    """
    try:
        operations_performed = []

        if req.sid:
            success = await sessions_store.bump_session_version(req.sid)
            operations_performed.append(f"sid:{req.sid}={'success' if success else 'not_found'}")

        if req.user_id:
            count = await sessions_store.bump_all_user_sessions(req.user_id)
            operations_performed.append(f"user_id:{req.user_id}={count}_sessions")

        if req.jti:
            ttl = remaining_ttl(req.jti)
            await sessions_store.blacklist_jti(req.jti, ttl_seconds=ttl)
            operations_performed.append(f"jti:{req.jti}={ttl}s_ttl")

        if operations_performed:
            logger.info(f"Revoke operations completed: {', '.join(operations_performed)}")
        else:
            logger.warning("Revoke called with no valid parameters", extra={"req": req.model_dump()})

    except Exception as e:
        # Don't 500; make it idempotent & observable
        logger.warning("revoke_error", extra={"err": str(e), "req": req.model_dump()})

    return Response(status_code=204)
