from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .error_envelope import build_error


def error_response(
    code: str,
    message: str,
    *,
    status: int,
    details: dict | None = None,
    headers: Mapping[str, str] | None = None,
):
    """Return a standardized JSONResponse with structured error details.

    Response format: {"code": code, "message": message, "details": details or {}}
    """
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))
    payload = {"code": code, "message": message, "details": details or {}}
    return JSONResponse(payload, status_code=status, headers=hdrs)


def unauthorized(
    *,
    code: str = "unauthorized",
    message: str = "Unauthorized",
    hint: str = "provide a valid bearer token or auth cookies",
    headers: Mapping[str, str] | None = None,
) -> HTTPException:
    """Return a standardized 401 HTTPException with structured detail.

    Detail shape: {code, message, hint}
    Includes a default WWW-Authenticate header unless headers overrides it.
    """
    # Include Deprecation header to ensure deprecated alias paths that resolve
    # to canonical handlers still emit this header when returning 401.
    hdrs = {"WWW-Authenticate": "Bearer", "X-Error-Code": code, "Deprecation": "true"}
    if headers:
        hdrs.update(dict(headers))
    env = build_error(code=code, message=message, hint=hint, meta={"status_code": 401})
    return HTTPException(status_code=401, detail=env, headers=hdrs)


def forbidden(
    *,
    code: str = "forbidden",
    message: str = "Forbidden",
    hint: str = "insufficient permissions for this action",
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a standardized 403 JSONResponse with structured error details."""
    details = {"status_code": 403, "hint": hint}
    return error_response(
        code=code, message=message, status=403, details=details, headers=headers
    )


def not_found(
    *,
    code: str = "not_found",
    message: str = "Not Found",
    hint: str = "the requested resource does not exist",
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a standardized 404 JSONResponse with structured error details."""
    details = {"status_code": 404, "hint": hint}
    return error_response(
        code=code, message=message, status=404, details=details, headers=headers
    )


def method_not_allowed(
    *,
    code: str = "method_not_allowed",
    message: str = "Method Not Allowed",
    hint: str = "check the allowed methods for this endpoint",
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a standardized 405 JSONResponse with structured error details."""
    details = {"status_code": 405, "hint": hint}
    return error_response(
        code=code, message=message, status=405, details=details, headers=headers
    )


def payload_too_large(
    *,
    code: str = "payload_too_large",
    message: str = "Payload Too Large",
    hint: str = "reduce the size of your request body",
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a standardized 413 JSONResponse with structured error details."""
    details = {"status_code": 413, "hint": hint}
    return error_response(
        code=code, message=message, status=413, details=details, headers=headers
    )


def validation_error(
    *,
    errors: list[dict[str, Any]] | None = None,
    code: str = "validation_error",
    message: str = "Validation Error",
    hint: str = "check your request data and try again",
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a standardized 422 JSONResponse for validation errors."""
    details = {"status_code": 422, "hint": hint}
    if errors:
        details["errors"] = errors

    return error_response(
        code=code, message=message, status=422, details=details, headers=headers
    )


def internal_error(
    *,
    code: str = "internal_error",
    message: str = "Internal Server Error",
    hint: str = "try again shortly",
    req_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a standardized 500 JSONResponse for internal errors."""
    details = {"status_code": 500, "hint": hint}
    if req_id:
        details["req_id"] = req_id

    return error_response(
        code=code, message=message, status=500, details=details, headers=headers
    )


def http_error(
    *,
    code: str,
    message: str,
    status: int = 400,
    hint: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> HTTPException:
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))
    env = build_error(
        code=code, message=message, hint=hint, meta={"status_code": status}
    )
    return HTTPException(status_code=status, detail=env, headers=hdrs)


def translate_validation_error(exc: ValidationError) -> HTTPException:
    """Translate Pydantic ValidationError to standardized HTTPException."""
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    # Build the standardized error response structure
    details = {"status_code": 422, "hint": "check your request data and try again"}
    if errors:
        details["errors"] = errors

    detail = {
        "code": "validation_error",
        "message": "Validation Error",
        "details": details,
    }

    return HTTPException(
        status_code=422, detail=detail, headers={"X-Error-Code": "validation_error"}
    )


def translate_common_exception(exc: Exception) -> HTTPException:
    """Translate common Python exceptions to appropriate HTTP status codes."""
    type(exc).__name__

    # Validation errors: pydantic's core ValidationError may come from
    # pydantic or pydantic_core; detect by the presence of an `errors()` method
    # instead of relying on a concrete class to support multiple pydantic versions.
    if hasattr(exc, "errors") and callable(getattr(exc, "errors", None)):
        return translate_validation_error(exc)

    # Authentication/Authorization errors
    if isinstance(exc, PermissionError):
        detail = {
            "code": "permission_denied",
            "message": "Permission denied",
            "details": {
                "status_code": 403,
                "hint": "insufficient permissions for this action",
            },
        }
        return HTTPException(
            status_code=403,
            detail=detail,
            headers={"X-Error-Code": "permission_denied"},
        )

    # Key/Value errors (often missing required fields)
    if isinstance(exc, KeyError):
        field = str(exc).strip("'\"")
        detail = {
            "code": "missing_required_field",
            "message": f"Missing required field: {field}",
            "details": {
                "status_code": 422,
                "hint": "check your request data and try again",
                "errors": [
                    {
                        "field": field,
                        "message": "Required field is missing",
                        "type": "missing",
                    }
                ],
            },
        }
        return HTTPException(
            status_code=422,
            detail=detail,
            headers={"X-Error-Code": "missing_required_field"},
        )

    # Type errors
    if isinstance(exc, TypeError):
        detail = {
            "code": "invalid_type",
            "message": "Type error in request data",
            "details": {
                "status_code": 422,
                "hint": "check your request data and try again",
                "errors": [
                    {"field": "request", "message": str(exc), "type": "type_error"}
                ],
            },
        }
        return HTTPException(
            status_code=422, detail=detail, headers={"X-Error-Code": "invalid_type"}
        )

    # Value errors (often invalid data)
    if isinstance(exc, ValueError):
        detail = {
            "code": "invalid_input",
            "message": "Invalid input data",
            "details": {
                "status_code": 422,
                "hint": "check your request data and try again",
                "errors": [
                    {"field": "request", "message": str(exc), "type": "value_error"}
                ],
            },
        }
        return HTTPException(
            status_code=422, detail=detail, headers={"X-Error-Code": "invalid_input"}
        )

    # Timeout errors
    if isinstance(exc, TimeoutError):
        detail = {
            "code": "timeout",
            "message": "Request timeout",
            "details": {"status_code": 504, "hint": "try again later"},
        }
        return HTTPException(
            status_code=504, detail=detail, headers={"X-Error-Code": "timeout"}
        )

    # Connection errors
    if isinstance(exc, ConnectionError):
        detail = {
            "code": "service_unavailable",
            "message": "Service temporarily unavailable",
            "details": {"status_code": 503, "hint": "try again shortly"},
        }
        return HTTPException(
            status_code=503,
            detail=detail,
            headers={"X-Error-Code": "service_unavailable"},
        )

    # File size exceeded
    if isinstance(exc, OSError) and "file too large" in str(exc).lower():
        detail = {
            "code": "payload_too_large",
            "message": "Payload Too Large",
            "details": {
                "status_code": 413,
                "hint": "reduce the size of your request body",
            },
        }
        return HTTPException(
            status_code=413,
            detail=detail,
            headers={"X-Error-Code": "payload_too_large"},
        )

    # Default to internal error for unhandled exceptions
    detail = {
        "code": "internal_error",
        "message": "Internal Server Error",
        "details": {"status_code": 500, "hint": "try again shortly"},
    }
    return HTTPException(
        status_code=500, detail=detail, headers={"X-Error-Code": "internal_error"}
    )


__all__ = [
    "unauthorized",
    "forbidden",
    "not_found",
    "method_not_allowed",
    "payload_too_large",
    "validation_error",
    "internal_error",
    "http_error",
    "translate_validation_error",
    "translate_common_exception",
]
