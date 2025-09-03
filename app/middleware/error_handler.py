from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import ValidationError

from ..error_envelope import build_error, shape_from_status
from ..logging_config import req_id_var
from ..http_errors import translate_common_exception, translate_validation_error

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

        # Use the new error translator for common exceptions
        try:
            # Translate the exception using our new translator
            translated_exc = translate_common_exception(exc)

            # Extract details from the translated exception
            status_code = translated_exc.status_code
            detail = getattr(translated_exc, "detail", {})
            code = detail.get("code", "internal_error") if isinstance(detail, dict) else "internal_error"
            message = detail.get("message", "Internal error") if isinstance(detail, dict) else "Internal error"
            hint = detail.get("hint") if isinstance(detail, dict) else None

        except Exception as translation_error:
            # Fallback if translation fails
            logger.warning(f"Error translation failed: {translation_error}, falling back to generic error")
            status_code = 500
            code = "internal_error"
            message = "Internal server error"
            hint = "try again shortly"

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
