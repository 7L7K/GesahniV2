from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..error_envelope import build_error


def raise_enveloped_error(
    code: str,
    message: str,
    *,
    status: int = 400,
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Raise a standardized HTTPException with ErrorEnvelope.

    This helper ensures all API errors use the consistent ErrorEnvelope format:
    {code, message, hint?, details?}

    Args:
        code: Machine-readable error code
        message: Human-readable error message
        status: HTTP status code (default: 400)
        hint: Optional actionable hint for the user
        details: Optional additional debug context (safe for clients)

    Raises:
        HTTPException: With standardized ErrorEnvelope detail
    """
    envelope = build_error(code=code, message=message, hint=hint, details=details)

    headers = {"X-Error-Code": code}

    raise HTTPException(status_code=status, detail=envelope, headers=headers)


def raise_bad_request(
    message: str,
    *,
    code: str = "bad_request",
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Raise a 400 Bad Request error with envelope."""
    raise_enveloped_error(
        code=code, message=message, status=400, hint=hint, details=details
    )


def raise_unauthorized(
    message: str = "unauthorized",
    *,
    code: str = "unauthorized",
    hint: str = "provide valid authentication credentials",
    details: dict[str, Any] | None = None,
) -> None:
    """Raise a 401 Unauthorized error with envelope."""
    raise_enveloped_error(
        code=code, message=message, status=401, hint=hint, details=details
    )


def raise_forbidden(
    message: str = "forbidden",
    *,
    code: str = "forbidden",
    hint: str = "you don't have permission for this action",
    details: dict[str, Any] | None = None,
) -> None:
    """Raise a 403 Forbidden error with envelope."""
    raise_enveloped_error(
        code=code, message=message, status=403, hint=hint, details=details
    )


def raise_not_found(
    message: str = "not found",
    *,
    code: str = "not_found",
    hint: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Raise a 404 Not Found error with envelope."""
    raise_enveloped_error(
        code=code, message=message, status=404, hint=hint, details=details
    )


def raise_conflict(
    message: str = "conflict",
    *,
    code: str = "conflict",
    hint: str = "resource already exists or is in an incompatible state",
    details: dict[str, Any] | None = None,
) -> None:
    """Raise a 409 Conflict error with envelope."""
    raise_enveloped_error(
        code=code, message=message, status=409, hint=hint, details=details
    )


def raise_internal_error(
    message: str = "internal error",
    *,
    code: str = "internal",
    hint: str = "try again shortly",
    details: dict[str, Any] | None = None,
) -> None:
    """Raise a 500 Internal Server Error with envelope."""
    raise_enveloped_error(
        code=code, message=message, status=500, hint=hint, details=details
    )


def raise_service_unavailable(
    message: str = "service temporarily unavailable",
    *,
    code: str = "service_unavailable",
    hint: str = "try again later",
    details: dict[str, Any] | None = None,
) -> None:
    """Raise a 503 Service Unavailable error with envelope."""
    raise_enveloped_error(
        code=code, message=message, status=503, hint=hint, details=details
    )


def validate_required_fields(data: dict[str, Any], required_fields: list[str]) -> None:
    """Validate that required fields are present in data.

    Args:
        data: The data dictionary to validate
        required_fields: List of field names that must be present

    Raises:
        HTTPException: With envelope if any required fields are missing
    """
    missing = [
        field for field in required_fields if field not in data or data[field] is None
    ]
    if missing:
        raise_bad_request(
            message=f"missing required fields: {', '.join(missing)}",
            code="missing_required_fields",
            hint="ensure all required fields are provided",
            details={"missing_fields": missing},
        )


def validate_field_type(field_name: str, value: Any, expected_type: type) -> None:
    """Validate that a field has the expected type.

    Args:
        field_name: Name of the field being validated
        value: The value to validate
        expected_type: The expected type

    Raises:
        HTTPException: With envelope if the type is incorrect
    """
    if not isinstance(value, expected_type):
        raise_bad_request(
            message=f"field '{field_name}' must be of type {expected_type.__name__}",
            code="invalid_field_type",
            hint=f"provide a {expected_type.__name__} value for '{field_name}'",
            details={
                "field": field_name,
                "provided_type": type(value).__name__,
                "expected_type": expected_type.__name__,
            },
        )


__all__ = [
    "raise_enveloped_error",
    "raise_bad_request",
    "raise_unauthorized",
    "raise_forbidden",
    "raise_not_found",
    "raise_conflict",
    "raise_internal_error",
    "raise_service_unavailable",
    "validate_required_fields",
    "validate_field_type",
]
