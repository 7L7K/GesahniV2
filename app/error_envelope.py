from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, TypedDict

from fastapi import HTTPException

from .logging_config import req_id_var

try:  # best-effort import
    from .otel_utils import get_trace_id_hex
except Exception:  # pragma: no cover

    def get_trace_id_hex() -> str | None:  # type: ignore
        return None


class ErrorEnvelope(TypedDict, total=False):
    code: str
    message: str
    detail: str  # For test compatibility
    hint: str | None
    meta: dict[str, Any]  # Changed from details to meta for chat route consistency


def _ulid() -> str:
    """Generate a ULID-like identifier without external deps.

    Follows ULID components (time + randomness) and Crockford base32 encoding.
    """
    import os as _os
    import time as _time

    ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

    def _encode(b: bytes) -> str:
        # base32 without padding, Crockford alphabet
        num = int.from_bytes(b, "big")
        out = []
        for _ in range(26):
            out.append(ENCODING[num & 31])
            num >>= 5
        return "".join(reversed(out))

    ts_ms = int(_time.time() * 1000)
    time_bytes = ts_ms.to_bytes(6, "big")
    rand_bytes = _os.urandom(10)
    return _encode(time_bytes + rand_bytes)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_error(
    *,
    code: str,
    message: str,
    hint: str | None = None,
    meta: dict[str, Any] | None = None,  # Changed from details to meta
) -> ErrorEnvelope:
    """Standard error envelope used across the API.

    Keys:
      - code (machine-readable)
      - message (human-readable)
      - detail (human-readable, for test compatibility)
      - hint (actionable hint for UI)
      - meta (debuggable context; safe for clients)
    """
    body: ErrorEnvelope = {"code": code, "message": message}
    # Add detail field for test compatibility (matches message)
    body["detail"] = message
    if hint is not None:
        body["hint"] = hint
    d = dict(meta or {})  # Changed from details to meta
    # Always enrich with request id and timestamp
    try:
        d.setdefault("req_id", req_id_var.get())
    except Exception:
        pass
    d.setdefault("timestamp", _now_iso())
    try:
        tid = get_trace_id_hex()
        if tid:
            d.setdefault("trace_id", tid)
    except Exception:
        pass
    # Ensure error_id is present for correlation
    d.setdefault("error_id", _ulid())
    # Expose environment for client-side branching when helpful
    env = os.getenv("ENV")
    if env:
        d.setdefault("env", env)
    if d:
        body["meta"] = d  # Changed from details to meta
    return body


def shape_from_status(
    status_code: int,
    *,
    default_message: str | None = None,
) -> tuple[str, str, str | None]:
    """Map HTTP status codes to canonical error code/message/hint."""
    code = "error"
    msg = default_message or "error"
    hint = None
    if status_code == 400:
        code, msg = "bad_request", default_message or "bad request"
    elif status_code == 401:
        # Use capitalized message for better client UX and test compatibility
        code, msg, hint = (
            "unauthorized",
            default_message or "Unauthorized",
            "missing or invalid token",
        )
    elif status_code == 403:
        code, msg, hint = (
            "forbidden",
            default_message or "forbidden",
            "missing scope or not allowed",
        )
    elif status_code == 404:
        code, msg = "not_found", default_message or "not found"
    elif status_code == 405:
        code, msg = "method_not_allowed", default_message or "method not allowed"
    elif status_code == 409:
        code, msg = "conflict", default_message or "conflict"
    elif status_code == 413:
        code, msg = "payload_too_large", default_message or "payload too large"
    elif status_code == 415:
        code, msg = (
            "unsupported_media_type",
            default_message or "unsupported media type",
        )
    elif status_code == 422:
        code, msg = "invalid_input", default_message or "invalid input"
    elif status_code == 429:
        code, msg = "quota", default_message or "quota exceeded"
    elif 500 <= status_code < 600:
        code, msg = "internal", default_message or "internal error"
    return code, msg, hint


def raise_enveloped(
    code: str,
    message: str,
    *,
    hint: str | None = None,
    meta: dict[str, Any] | None = None,  # Changed from details to meta
    status: int = 400,
):
    """Raise a FastAPI HTTPException carrying a standard envelope.

    Raw HTTPException should be avoided; prefer this helper.
    """

    env = build_error(
        code=code, message=message, hint=hint, meta=meta
    )  # Changed from details to meta
    headers = {"X-Error-Code": code}
    raise HTTPException(status_code=status, detail=env, headers=headers)


def validate_error_envelope(envelope: dict) -> bool:
    """Validate that an error envelope conforms to the required {code, message, meta} format.

    Returns True if valid, raises ValueError if invalid.
    """
    if not isinstance(envelope, dict):
        raise ValueError("Error envelope must be a dictionary")

    required_keys = {"code", "message", "meta"}
    missing_keys = required_keys - set(envelope.keys())
    if missing_keys:
        raise ValueError(f"Error envelope missing required keys: {missing_keys}")

    if not isinstance(envelope["code"], str):
        raise ValueError("Error envelope 'code' must be a string")

    if not isinstance(envelope["message"], str):
        raise ValueError("Error envelope 'message' must be a string")

    if not isinstance(envelope["meta"], dict):
        raise ValueError("Error envelope 'meta' must be a dictionary")

    return True


def enveloped_route(fn):
    """Decorator to auto-wrap unhandled exceptions with a standard envelope."""

    import functools

    @functools.wraps(fn)
    async def _inner(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            raise_enveloped(
                "internal",
                "internal error",
                hint="try again shortly",
                meta={"error": str(e)},  # Changed from details to meta
                status=500,
            )

    return _inner
