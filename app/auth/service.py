"""Shared helpers for auth endpoints (logging and token helpers)."""

import logging
import os
from typing import Any

from fastapi import Request, Response

from app.csrf import issue_csrf_token
logger = logging.getLogger(__name__)


async def log_request_meta(request: Request):
    """Log detailed request metadata for debugging auth issues."""
    import time
    import uuid

    # Generate unique request ID for tracing
    req_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    try:
        logger.info(
            "\U0001f510 AUTH REQUEST DEBUG - START",
            extra={
                "req_id": req_id,
                "function": "log_request_meta",
                "phase": "entry",
                "timestamp": start_time,
                "request_id": getattr(request, "request_id", "none"),
                "url": str(request.url),
                "method": request.method,
            }
        )

        # Extract request metadata with comprehensive logging
        cookies = list(request.cookies.keys()) if hasattr(request, "cookies") else []
        origin = request.headers.get("origin", "none")
        referer = request.headers.get("referer", "none")
        user_agent = request.headers.get("user-agent", "none")
        content_type = request.headers.get("content-type", "none")
        authorization = request.headers.get("authorization", "none")

        # Log security-relevant headers
        security_headers = {
            "authorization": authorization[:50] + "..." if authorization and len(authorization) > 50 else authorization,
            "x-forwarded-for": request.headers.get("x-forwarded-for", "none"),
            "x-real-ip": request.headers.get("x-real-ip", "none"),
            "cf-connecting-ip": request.headers.get("cf-connecting-ip", "none"),
            "x-api-key": request.headers.get("x-api-key", "none"),
        }

        # Log cookie details
        cookie_details = {}
        if hasattr(request, "cookies") and request.cookies:
            for name, value in request.cookies.items():
                cookie_details[name] = {
                    "present": True,
                    "length": len(value),
                    "prefix": value[:20] + "..." if len(value) > 20 else value,
                }

        client_ip = (
            getattr(request.client, "host", "unknown")
            if request.client
            else "unknown"
        )
        client_port = (
            getattr(request.client, "port", "unknown")
            if request.client
            else "unknown"
        )

        # Log comprehensive request metadata
        logger.info(
            "\U0001f510 AUTH REQUEST DEBUG - METADATA",
            extra={
                "req_id": req_id,
                "function": "log_request_meta",
                "phase": "metadata_extraction",
                "meta": {
                    "path": request.url.path,
                    "method": request.method,
                    "origin": origin,
                    "referer": referer,
                    "user_agent": user_agent,
                    "content_type": content_type,
                    "content_length": request.headers.get("content-length", "none"),
                    "accept": request.headers.get("accept", "none"),
                    "accept_encoding": request.headers.get("accept-encoding", "none"),
                    "client_ip": client_ip,
                    "client_port": client_port,
                    "query_params": dict(request.query_params),
                    "query_param_count": len(request.query_params),
                    "cookies_present": len(cookies) > 0,
                    "cookie_names": cookies,
                    "cookie_count": len(cookies),
                    "cookie_details": cookie_details,
                    "has_auth_header": bool(authorization and authorization != "none"),
                    "auth_header_type": authorization.split()[0] if authorization and " " in authorization else "none",
                    "security_headers": security_headers,
                    "all_headers_count": len(request.headers),
                    "request_state": getattr(request, "state", {}),
                }
            }
        )

        # Log potential security issues
        security_warnings = []
        if not authorization or authorization == "none":
            security_warnings.append("no_auth_header")
        if len(cookies) == 0:
            security_warnings.append("no_cookies")
        if client_ip == "unknown":
            security_warnings.append("unknown_client_ip")

        if security_warnings:
            logger.warning(
                "\U0001f510 AUTH REQUEST DEBUG - SECURITY WARNINGS",
                extra={
                    "req_id": req_id,
                    "function": "log_request_meta",
                    "phase": "security_check",
                    "warnings": security_warnings,
                    "path": request.url.path,
                    "client_ip": client_ip,
                }
            )

        processing_time = time.time() - start_time

        logger.info(
            "\U0001f510 AUTH REQUEST DEBUG - COMPLETE",
            extra={
                "req_id": req_id,
                "function": "log_request_meta",
                "phase": "exit",
                "processing_time_ms": round(processing_time * 1000, 2),
                "timestamp": time.time(),
                "success": True,
            }
        )

        return request

    except Exception as e:
        processing_time = time.time() - start_time

        logger.error(
            "\U0001f510 AUTH REQUEST DEBUG - ERROR",
            extra={
                "req_id": req_id,
                "function": "log_request_meta",
                "phase": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "processing_time_ms": round(processing_time * 1000, 2),
                "path": getattr(request, "url", {}).path if hasattr(request, "url") else "unknown",
                "method": getattr(request, "method", "unknown"),
            },
            exc_info=True
        )
        raise


def should_rotate_access(user_id: str) -> bool:
    """Determine if access token should be rotated based on user ID and policy."""
    return bool(user_id and user_id != "anon")


def mint_access_token(user_id: str) -> str:
    """Mint a new access token with guard against empty tokens."""
    if not user_id or user_id == "anon":
        from app.http_errors import http_error

        raise http_error(
            code="ERR_CANNOT_MINT_TOKEN_FOR_INVALID_USER",
            message="Cannot mint token for invalid user",
            status=500,
        )

    try:
        from app.cookie_config import get_token_ttls
        from app.tokens import make_access

        access_ttl, _ = get_token_ttls()
        token = make_access({"user_id": user_id}, ttl_s=access_ttl)

        if not token or not isinstance(token, str) or len(token.strip()) == 0:
            logger.error(f"Empty token generated for user {user_id}")
            from app.http_errors import http_error

            raise http_error(
                code="ERR_TOKEN_GEN_FAILED",
                message="Token generation failed",
                status=500,
            )

        return token
    except Exception as e:
        logger.error(f"Token minting failed for user {user_id}: {e}")
        from app.http_errors import http_error

        raise http_error(
            code="ERR_TOKEN_GEN_FAILED", message="Token generation failed", status=500
        ) from e


class AuthService:
    """Orchestration service for authentication operations.

    Provides a clean service seam that:
    - Handles lazy refresh on whoami
    - Orchestrates token rotation on /auth/refresh
    - Manages cookie/session clearing on logout
    - Makes router functions become one-liners
    """

    @staticmethod
    async def whoami_with_lazy_refresh(
        request: Request, response: Response
    ) -> dict[str, Any]:
        """Perform whoami with lazy refresh if tokens are near expiration.

        Returns the whoami response data with tokens refreshed if needed.
        """
        from app.auth.whoami_impl import whoami_impl

        # First get current authentication state
        whoami_response = await whoami_impl(request)

        # Check if we should perform lazy refresh
        if await AuthService._should_lazy_refresh(request):
            try:
                await AuthService._perform_lazy_refresh(request, response)
                logger.info("whoami.lazy_refresh.performed")
            except Exception as e:
                logger.warning(f"whoami.lazy_refresh.failed: {e}")

        return whoami_response

    @staticmethod
    async def _should_lazy_refresh(request: Request) -> bool:
        """Determine if lazy refresh should be performed."""
        import time

        from app.auth.jwt_utils import _decode_any
        from app.cookies import read_access_cookie

        # Only refresh if we have a valid access token
        access_token = read_access_cookie(request)
        if not access_token:
            return False

        try:
            # Decode token to check expiration
            claims = _decode_any(access_token)
            if not isinstance(claims, dict) or "exp" not in claims:
                return False

            exp_time = claims["exp"]
            current_time = time.time()

            # Refresh if token expires within 5 minutes
            refresh_threshold = 300  # 5 minutes
            return (exp_time - current_time) < refresh_threshold

        except Exception:
            return False

    @staticmethod
    async def _perform_lazy_refresh(request: Request, response: Response) -> None:
        """Perform lazy refresh of tokens."""
        from app.auth_refresh import rotate_refresh_token
        from app.deps.user import get_current_user_id

        try:
            user_id = await get_current_user_id(request=request)
            if user_id and user_id != "anon":
                tokens = await rotate_refresh_token(user_id, request, response)
                if tokens:
                    logger.info(f"lazy_refresh.success user_id={user_id}")
                else:
                    logger.info(f"lazy_refresh.no_rotation_needed user_id={user_id}")
        except Exception as e:
            logger.warning(f"lazy_refresh.error: {e}")
            raise

    @staticmethod
    async def refresh_tokens(request: Request, response: Response, refresh_token: str | None = None) -> dict[str, Any]:
        """Orchestrate token refresh with proper error handling and metrics."""
        import time

        from app.auth_refresh import rotate_refresh_token
        from app.deps.user import get_current_user_id
        from app.metrics_auth import (
            record_auth_operation,
            record_error_code,
            record_refresh_latency,
            refresh_rotation_failed,
            refresh_rotation_success,
        )

        start_time = time.time()

        try:
            user_id = await get_current_user_id(request=request)
            if not user_id or user_id == "anon":
                from app.auth.errors import ERR_INVALID_REFRESH
                from app.http_errors import unauthorized

                record_error_code(ERR_INVALID_REFRESH, "/v1/auth/refresh", "error")
                record_auth_operation("refresh", "failed", "/v1/auth/refresh")
                raise unauthorized(
                    code=ERR_INVALID_REFRESH, message="invalid refresh token"
                )

            # Perform the actual refresh with optional explicit refresh token
            tokens = await rotate_refresh_token(user_id, request, response, refresh_token)

            if tokens:
                refresh_rotation_success("/v1/auth/refresh")
                record_auth_operation("refresh", "success", "/v1/auth/refresh")
                logger.info(f"refresh.success user_id={user_id}")
                duration = int((time.time() - start_time) * 1000)
                record_refresh_latency("rotation", duration)

                # Generate new CSRF token on successful refresh
                csrf_token = None
                try:
                    csrf_token = issue_csrf_token(response, request)
                except Exception as exc:  # pragma: no cover - best effort
                    logger.debug(f"csrf.token_generation_failed: {exc}")

                # Return standardized response
                response.headers["Cache-Control"] = "no-store"
                try:
                    del response.headers["ETag"]
                except KeyError:
                    pass
                response.status_code = 200

                return {
                    "rotated": True,
                    "access_token": tokens.get("access_token"),
                    "user_id": tokens.get("user_id", user_id),
                    "csrf_token": csrf_token,
                    "csrf": csrf_token,
                }
            else:
                refresh_rotation_success("/v1/auth/refresh")
                record_auth_operation("refresh", "no_rotation", "/v1/auth/refresh")
                logger.info(f"refresh.no_rotation_needed user_id={user_id}")
                duration = int((time.time() - start_time) * 1000)
                record_refresh_latency("no_rotation", duration)

                # Generate new CSRF token even when no rotation needed
                csrf_token = None
                try:
                    csrf_token = issue_csrf_token(response, request)
                except Exception as exc:  # pragma: no cover - best effort
                    logger.debug(f"csrf.token_generation_failed: {exc}")

                response.headers["Cache-Control"] = "no-store"
                try:
                    del response.headers["ETag"]
                except KeyError:
                    pass
                response.status_code = 200

                return {
                    "rotated": False,
                    "access_token": None,
                    "user_id": user_id,
                    "csrf_token": csrf_token,
                    "csrf": csrf_token,
                }

        except Exception as e:
            # Record error metrics
            error_code = getattr(e, "code", "unknown_error")
            record_error_code(error_code, "/v1/auth/refresh", "error")
            record_auth_operation("refresh", "failed", "/v1/auth/refresh")
            refresh_rotation_failed("unknown", "/v1/auth/refresh")

            duration = int((time.time() - start_time) * 1000)
            record_refresh_latency("error", duration)
            logger.error(f"refresh.error: {e}")
            raise

    @staticmethod
    async def logout_user(request: Request, response: Response, user_id: str) -> None:
        """Orchestrate user logout with cookie and session cleanup."""
        from app.session_store import get_session_store
        from app.auth.rate_limit_utils import _get_refresh_ttl_seconds
        from app.cookies import (
            clear_auth_cookies,
            clear_device_cookie,
            read_session_cookie,
        )
        from app.deps.user import resolve_session_id
        from app.metrics_auth import record_auth_operation
        from app.token_store import revoke_refresh_family

        logger.info(f"🚪 LOGOUT_SERVICE_STEP_1: Starting logout service for user_id={user_id}")

        # Revoke refresh token family
        try:
            logger.info(f"🚪 LOGOUT_SERVICE_STEP_2: Resolving session ID from request")
            sid = resolve_session_id(request=request)
            logger.info(f"🚪 LOGOUT_SERVICE_STEP_3: Resolved session ID: {sid}")
            await revoke_refresh_family(sid, ttl_seconds=_get_refresh_ttl_seconds())
            logger.info(f"🚪 LOGOUT_SERVICE_STEP_4: Revoked refresh token family for session_id={sid}")
        except Exception as e:
            logger.warning(f"🚪 LOGOUT_SERVICE_ERROR: Refresh token revocation failed: {e}")

        # Delete session
        try:
            logger.info(f"🚪 LOGOUT_SERVICE_STEP_5: Reading session cookie from request")
            session_id = read_session_cookie(request)
            if session_id:
                logger.info(f"🚪 LOGOUT_SERVICE_STEP_6: Found session cookie: {session_id}")
                store = get_session_store()
                store.delete_session(session_id)
                logger.info(f"🚪 LOGOUT_SERVICE_STEP_7: Deleted session: {session_id}")
            else:
                logger.info(f"🚪 LOGOUT_SERVICE_STEP_6: No session cookie found")
        except Exception as e:
            logger.warning(f"🚪 LOGOUT_SERVICE_ERROR: Session deletion failed: {e}")

        # Clear cookies with consistent device cookie handling
        try:
            logger.info(f"🚪 LOGOUT_SERVICE_STEP_8: Clearing authentication cookies")
            clear_auth_cookies(response, request)

            # Clear canonical device cookie
            logger.info(f"🚪 LOGOUT_SERVICE_STEP_9: Clearing device cookie")
            clear_device_cookie(response, request, cookie_name="device_id")

            # Clear legacy device cookies if AUTH_LEGACY_COOKIE_NAMES=1
            if os.getenv("AUTH_LEGACY_COOKIE_NAMES", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                try:
                    clear_device_cookie(
                        response, request, cookie_name="device_id_legacy"
                    )
                    logger.info("logout.legacy_device_cookie_cleared")
                except Exception:
                    pass

            logger.info("logout.cookies_cleared")

            # Add Clear-Site-Data header for belt-and-suspenders cookie clearing
            response.headers["Clear-Site-Data"] = '"cookies"'

            # Also clear legacy cookies if available
            try:
                from app.web.cookies import clear_auth_cookies as _web_clear

                _web_clear(response, request)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"logout.cookie_clear_failed: {e}")

        # Record successful logout operation
        record_auth_operation("logout", "success", "/v1/auth/logout")
        logger.info(f"logout.complete user_id={user_id}")

    @staticmethod
    async def logout_all_sessions(
        request: Request, response: Response, user_id: str
    ) -> None:
        """Orchestrate logout from all sessions for this user."""
        from app.session_store import get_session_store
        from app.auth.rate_limit_utils import _get_refresh_ttl_seconds
        from app.cookies import (
            clear_auth_cookies,
            clear_device_cookie,
            read_session_cookie,
        )
        from app.deps.user import resolve_session_id_strict
        from app.metrics_auth import record_auth_operation
        from app.token_store import revoke_refresh_family

        logger.info(f"logout_all.start user_id={user_id}")

        # Revoke entire refresh family
        try:
            sid = resolve_session_id_strict(request=request)
            if sid:
                await revoke_refresh_family(sid, ttl_seconds=_get_refresh_ttl_seconds())
                logger.info(f"logout_all.family_revoked session_id={sid}")
        except Exception as e:
            logger.warning(f"logout_all.family_revoke_failed: {e}")

        # Delete current session
        try:
            session_id = read_session_cookie(request)
            if session_id:
                store = get_session_store()
                store.delete_session(session_id)
                logger.info(f"logout_all.session_deleted session_id={session_id}")
        except Exception as e:
            logger.warning(f"logout_all.session_delete_failed: {e}")

        # Clear cookies with consistent device cookie handling
        try:
            clear_auth_cookies(response, request)

            # Clear canonical device cookie
            clear_device_cookie(response, request, cookie_name="device_id")

            # Clear legacy device cookies if AUTH_LEGACY_COOKIE_NAMES=1
            if os.getenv("AUTH_LEGACY_COOKIE_NAMES", "0").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                try:
                    clear_device_cookie(
                        response, request, cookie_name="device_id_legacy"
                    )
                    logger.info("logout_all.legacy_device_cookie_cleared")
                except Exception:
                    pass

            logger.info("logout_all.cookies_cleared")
        except Exception as e:
            logger.warning(f"logout_all.cookie_clear_failed: {e}")

        # Record successful logout_all operation
        record_auth_operation("logout_all", "success", "/v1/auth/logout_all")
        logger.info(f"logout_all.complete user_id={user_id}")
