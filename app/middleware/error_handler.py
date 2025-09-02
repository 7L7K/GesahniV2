from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from ..error_envelope import build_error, shape_from_status
from ..logging_config import req_id_var

try:  # best-effort import
    from ..otel_utils import get_trace_id_hex
except Exception:  # pragma: no cover

    def get_trace_id_hex() -> str | None:  # type: ignore
        return None


logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware that enhances error handling with standardized ErrorEnvelope responses."""

    async def dispatch(self, request: Request, call_next):
        """Process request and ensure error responses use ErrorEnvelope format."""
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            return await self._handle_exception(request, exc)

    async def _handle_exception(self, request: Request, exc: Exception) -> Any:
        """Handle exceptions and return standardized ErrorEnvelope responses."""
        req_id = req_id_var.get() or "-"

        # If it's already an HTTPException with proper envelope, let it through
        if isinstance(exc, HTTPException):
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict) and "code" in detail and "message" in detail:
                # Already properly formatted, just ensure headers have error code
                headers = dict(getattr(exc, "headers", {}))
                code = detail.get("code")
                if code and "X-Error-Code" not in headers:
                    headers["X-Error-Code"] = str(code)
                exc.headers = headers
                raise exc

        # Convert other exceptions to standardized envelope
        status_code = 500
        code = "internal"
        message = "internal error"
        hint = "try again shortly"

        if isinstance(exc, HTTPException):
            status_code = exc.status_code
            code, message, hint = shape_from_status(status_code, default_message=exc.detail)
        elif isinstance(exc, ValueError):
            status_code = 400
            code = "invalid_input"
            message = str(exc) or "invalid input"
            hint = "check your request data"
        elif isinstance(exc, KeyError):
            status_code = 400
            code = "missing_required_field"
            message = f"missing required field: {str(exc)}"
            hint = "ensure all required fields are provided"
        elif isinstance(exc, TypeError):
            status_code = 400
            code = "invalid_type"
            message = str(exc) or "type error"
            hint = "check data types in your request"
        elif isinstance(exc, PermissionError):
            status_code = 403
            code = "permission_denied"
            message = "permission denied"
            hint = "you don't have permission for this action"
        elif isinstance(exc, TimeoutError):
            status_code = 504
            code = "timeout"
            message = "request timeout"
            hint = "try again later"
        elif isinstance(exc, ConnectionError):
            status_code = 503
            code = "service_unavailable"
            message = "service temporarily unavailable"
            hint = "try again shortly"
        else:
            # Generic internal error
            pass

        # Build envelope with enhanced details
        details = {
            "status_code": status_code,
            "req_id": req_id,
            "path": request.url.path,
            "method": request.method,
        }

        # Add trace ID if available
        tid = get_trace_id_hex()
        if tid:
            details["trace_id"] = tid

        envelope = build_error(code=code, message=message, hint=hint, details=details)

        # Log the error with structured data
        logger.error(
            f"Request failed: {request.method} {request.url.path} -> {type(exc).__name__}",
            extra={
                "meta": {
                    "req_id": req_id,
                    "status_code": status_code,
                    "error_code": code,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "path": request.url.path,
                    "method": request.method,
                    "trace_id": tid,
                }
            },
            exc_info=True,
        )

        # Return a JSONResponse with the standardized envelope and headers so
        # TestClient gets a normal response object instead of an exception.
        from fastapi.responses import JSONResponse

        headers = {"X-Error-Code": code}
        if tid:
            headers["X-Trace-ID"] = tid

        return JSONResponse(status_code=status_code, content=envelope, headers=headers)
