from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

# Import your existing function middlewares so we reuse their logic
from .middleware_core import reload_env_middleware as _reload_env_fn
from .middleware_core import silent_refresh_middleware as _silent_refresh_fn


def _generate_error_code(status_code: int, error_type: str = None) -> str:
    """Generate concise error code for 4xx/5xx responses."""
    if 400 <= status_code < 500:
        prefix = "CLIENT"
        category = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            413: "PAYLOAD_TOO_LARGE",
            415: "UNSUPPORTED_MEDIA_TYPE",
            422: "UNPROCESSABLE_ENTITY",
            429: "TOO_MANY_REQUESTS",
        }.get(status_code, "CLIENT_ERROR")
    elif 500 <= status_code < 600:
        prefix = "SERVER"
        category = {
            500: "INTERNAL_ERROR",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE",
            504: "GATEWAY_TIMEOUT",
        }.get(status_code, "SERVER_ERROR")
    else:
        return f"HTTP_{status_code}"

    if error_type:
        # Add specific error type for server errors
        error_suffix = {
            "ValueError": "VALIDATION",
            "TypeError": "TYPE",
            "AttributeError": "ATTRIBUTE",
            "KeyError": "KEY_MISSING",
            "HTTPException": "HTTP_EXCEPTION",
            "JWTError": "JWT_INVALID",
            "ConnectionError": "CONNECTION",
            "TimeoutError": "TIMEOUT",
        }.get(error_type, "UNKNOWN")

        return f"{prefix}_{category}_{error_suffix}"

    return f"{prefix}_{category}"


# ===== Enhanced Error Handling (class wrapper around your function body) =====
class EnhancedErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Wraps the enhanced_error_handling(request, call_next) function semantics
    into a class middleware so we can control order with add_middleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable]
    ):
        # Inline the logic from your enhanced_error_handling function:
        import time
        from datetime import datetime

        from app.logging_config import req_id_var

        logger = logging.getLogger(__name__)
        start_time = time.time()
        req_id = req_id_var.get()
        route_name = None
        user_anon = "local"

        try:
            try:
                route_name = getattr(request.scope.get("endpoint"), "__name__", None)
            except Exception:
                route_name = None

            # anonymize auth header like your helper does
            try:
                auth_header = request.headers.get("authorization")
                if auth_header:
                    import hashlib

                    token = auth_header.split()[-1]
                    user_anon = hashlib.md5(token.encode()).hexdigest()
            except Exception:
                user_anon = "local"

            logger.debug(
                f"Request started: {request.method} {request.url.path} (ID: {req_id})"
            )
            if logger.isEnabledFor(logging.DEBUG):
                headers = dict(request.headers)
                for key in ["authorization", "cookie", "x-api-key"]:
                    if key in headers:
                        headers[key] = "[REDACTED]"
                logger.debug(
                    f"Request details: {request.method} {request.url.path}",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "route": route_name,
                            "user_anon": user_anon,
                            "headers": headers,
                            "query_params": dict(request.query_params),
                            "client_ip": (
                                request.client.host if request.client else None
                            ),
                        }
                    },
                )

            response = await call_next(request)
            duration = time.time() - start_time

            # Add error code for 4xx/5xx responses
            error_code = None
            if 400 <= response.status_code < 600:
                error_code = _generate_error_code(response.status_code)

            log_extra = {
                "req_id": req_id,
                "route": route_name,
                "user_anon": user_anon,
                "status_code": response.status_code,
                "duration_ms": duration * 1000,
            }
            if error_code:
                log_extra["error_code"] = error_code

            logger.info(
                f"Request completed: {request.method} {request.url.path} -> {response.status_code} ({duration:.3f}s)",
                extra={"meta": log_extra},
            )
            return response

        except Exception as e:
            duration = time.time() - start_time

            # Generate error code for server errors
            error_code = _generate_error_code(500, type(e).__name__)

            logger.error(
                f"Request failed: {request.method} {request.url.path} -> {type(e).__name__}: {e}",
                exc_info=True,
                extra={
                    "meta": {
                        "req_id": req_id,
                        "route": route_name,
                        "user_anon": user_anon,
                        "duration_ms": duration * 1000,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "error_code": error_code,
                    }
                },
            )
            # unify error shape
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "req_id": req_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )


# ===== Silent Refresh as a class wrapper (reuses your function) =====
class SilentRefreshMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable]
    ):
        return await _silent_refresh_fn(request, call_next)


# ===== Reload Env as a class wrapper (reuses your function; dev-only) =====
class ReloadEnvMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable]
    ):
        return await _reload_env_fn(request, call_next)


# Notes
# We intentionally wrap your existing function middlewares so behavior is unchanged.
# If you prefer, you can later move the bodies directly into the classes and delete the functions.
