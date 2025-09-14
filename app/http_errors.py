from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from .error_envelope import build_error


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
) -> HTTPException:
    """Return a standardized 403 HTTPException with structured detail."""
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))
    env = build_error(code=code, message=message, hint=hint, meta={"status_code": 403})
    return HTTPException(status_code=403, detail=env, headers=hdrs)


def not_found(
    *,
    code: str = "not_found",
    message: str = "Not Found",
    hint: str = "the requested resource does not exist",
    headers: Mapping[str, str] | None = None,
) -> HTTPException:
    """Return a standardized 404 HTTPException with structured detail."""
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))
    env = build_error(code=code, message=message, hint=hint, meta={"status_code": 404})
    return HTTPException(status_code=404, detail=env, headers=hdrs)


def method_not_allowed(
    *,
    code: str = "method_not_allowed",
    message: str = "Method Not Allowed",
    hint: str = "check the allowed methods for this endpoint",
    headers: Mapping[str, str] | None = None,
) -> HTTPException:
    """Return a standardized 405 HTTPException with structured detail."""
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))
    env = build_error(code=code, message=message, hint=hint, meta={"status_code": 405})
    return HTTPException(status_code=405, detail=env, headers=hdrs)


def payload_too_large(
    *,
    code: str = "payload_too_large",
    message: str = "Payload Too Large",
    hint: str = "reduce the size of your request body",
    headers: Mapping[str, str] | None = None,
) -> HTTPException:
    """Return a standardized 413 HTTPException with structured detail."""
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))
    env = build_error(code=code, message=message, hint=hint, meta={"status_code": 413})
    return HTTPException(status_code=413, detail=env, headers=hdrs)


def validation_error(
    *,
    errors: list[dict[str, Any]] | None = None,
    code: str = "validation_error",
    message: str = "Validation Error",
    hint: str = "check your request data and try again",
    headers: Mapping[str, str] | None = None,
) -> HTTPException:
    """Return a standardized 422 HTTPException for validation errors."""
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))

    meta = {"status_code": 422}
    if errors:
        meta["errors"] = errors

    env = build_error(code=code, message=message, hint=hint, meta=meta)
    return HTTPException(status_code=422, detail=env, headers=hdrs)


def internal_error(
    *,
    code: str = "internal_error",
    message: str = "Internal Server Error",
    hint: str = "try again shortly",
    req_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> HTTPException:
    """Return a standardized 500 HTTPException for internal errors."""
    hdrs = {"X-Error-Code": code}
    if headers:
        hdrs.update(dict(headers))

    meta = {"status_code": 500}
    if req_id:
        meta["req_id"] = req_id

    env = build_error(code=code, message=message, hint=hint, meta=meta)
    return HTTPException(status_code=500, detail=env, headers=hdrs)


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

    return validation_error(errors=errors)


def translate_common_exception(exc: Exception) -> HTTPException:
    """Translate common Python exceptions to appropriate HTTP status codes."""
    exc_type = type(exc).__name__

    # Validation errors: pydantic's core ValidationError may come from
    # pydantic or pydantic_core; detect by the presence of an `errors()` method
    # instead of relying on a concrete class to support multiple pydantic versions.
    if hasattr(exc, "errors") and callable(getattr(exc, "errors", None)):
        return translate_validation_error(exc)

    # Authentication/Authorization errors
    if isinstance(exc, PermissionError):
        return forbidden(code="permission_denied", message="Permission denied")

    # Key/Value errors (often missing required fields)
    if isinstance(exc, KeyError):
        field = str(exc).strip("'\"")
        return validation_error(
            errors=[
                {
                    "field": field,
                    "message": "Required field is missing",
                    "type": "missing",
                }
            ],
            code="missing_required_field",
            message=f"Missing required field: {field}",
        )

    # Type errors
    if isinstance(exc, TypeError):
        return validation_error(
            errors=[{"field": "request", "message": str(exc), "type": "type_error"}],
            code="invalid_type",
            message="Type error in request data",
        )

    # Value errors (often invalid data)
    if isinstance(exc, ValueError):
        return validation_error(
            errors=[{"field": "request", "message": str(exc), "type": "value_error"}],
            code="invalid_input",
            message="Invalid input data",
        )

    # Timeout errors
    if isinstance(exc, TimeoutError):
        return http_error(
            code="timeout",
            message="Request timeout",
            status=504,
            hint="try again later",
        )

    # Connection errors
    if isinstance(exc, ConnectionError):
        return http_error(
            code="service_unavailable",
            message="Service temporarily unavailable",
            status=503,
            hint="try again shortly",
        )

    # File size exceeded
    if isinstance(exc, OSError) and "file too large" in str(exc).lower():
        return payload_too_large()

    # Default to internal error for unhandled exceptions
    return internal_error()


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
