"""Application-level errors and standardized error handlers."""

from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class BackendUnavailableError(RuntimeError):
    """Raised when a configured backend cannot be resolved at startup."""

    def __init__(self, message: str):
        super().__init__(message)


def json_error(
    code: str, message: str, status: int, meta: dict[str, Any] | None = None
) -> JSONResponse:
    """Create a standardized JSON error response.

    This enforces the contract: {"code", "message", "meta"} structure
    that our tests verify. Lowercase codes for consistency.
    """
    return JSONResponse(
        {"code": code.lower(), "message": message, "meta": meta or {}},
        status_code=status,
    )


async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global error handler that enforces error response contract.

    Maps exceptions to standardized error responses with consistent shape.
    """
    req_id = request.headers.get("x-request-id") or "-"
    now = datetime.utcnow().isoformat() + "Z"

    base_meta = {"request_id": req_id, "timestamp": now}

    # Map common exceptions to standardized responses
    if isinstance(exc, HTTPException):
        # FastAPI HTTPException - map status codes to specific error codes
        status_to_code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            422: "validation_error",
            429: "rate_limited",
            500: "internal_error",
            502: "bad_gateway",
            503: "service_unavailable",
            504: "timeout",
        }

        code = status_to_code.get(exc.status_code, "http_error")
        return json_error(
            code=code,
            message=exc.detail,
            status=exc.status_code,
            meta={**base_meta, "original_status": exc.status_code},
        )

    elif isinstance(exc, ValueError):
        # Validation errors
        return json_error("validation_error", "Invalid input data", 422, meta=base_meta)

    elif isinstance(exc, PermissionError):
        # Permission/authorization errors
        return json_error("forbidden", "Access denied", 403, meta=base_meta)

    elif isinstance(exc, TimeoutError):
        # Timeout errors
        return json_error("timeout", "Request timed out", 504, meta=base_meta)

    elif isinstance(exc, ConnectionError):
        # Connection/network errors
        return json_error(
            "connection_error", "Service temporarily unavailable", 503, meta=base_meta
        )

    elif isinstance(exc, FileNotFoundError):
        # File/resource not found
        return json_error("not_found", "Resource not found", 404, meta=base_meta)

    else:
        # Generic internal server error
        return json_error("internal_error", "Something went wrong", 500, meta=base_meta)


def register_error_handlers(app):
    """Register standardized error handlers on the FastAPI app.

    This ensures all error responses follow the same contract shape
    that our tests enforce.
    """
    # Add global exception handler
    app.add_exception_handler(Exception, global_error_handler)

    # Add specific HTTP exception handler (FastAPI's built-in)
    app.add_exception_handler(HTTPException, global_error_handler)
