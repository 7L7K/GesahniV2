from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.error_envelope import build_error, shape_from_status, validate_error_envelope
from app.otel_utils import get_trace_id_hex

log = logging.getLogger(__name__)


def _trace_details(request: Request, status: int) -> dict[str, Any]:
    try:
        tid = get_trace_id_hex()
    except Exception:
        tid = None
    return {
        "status_code": status,
        "trace_id": tid,
        "path": request.url.path,
        "method": getattr(
            request, "method", "WS"
        ),  # WebSocket requests don't have method attribute
    }


async def handle_http_error(request: Request, exc: StarletteHTTPException):
    # Pass through already-structured payloads, but normalize headers/ids.
    status = getattr(exc, "status_code", 500)
    headers = dict(getattr(exc, "headers", {}) or {})
    detail = getattr(exc, "detail", None)

    if isinstance(detail, dict) and ("code" in detail or "error" in detail):
        shaped = dict(detail)
        # Tag envelope/ids in headers for client correlation
        try:
            code_hdr = shaped.get("code") or shaped.get("error")
            if code_hdr:
                headers["X-Error-Code"] = str(code_hdr)
            det = shaped.get("details") or {}
            if isinstance(det, dict):
                if det.get("error_id"):
                    headers["X-Error-ID"] = str(det["error_id"])
                if det.get("trace_id"):
                    headers["X-Trace-ID"] = str(det["trace_id"])
        except Exception:
            pass

        # Ensure deprecated alias paths emit Deprecation header even when served by canonical handlers
        try:
            if request.url.path in {"/v1/whoami", "/v1/me", "/whoami", "/me"}:
                headers.setdefault("Deprecation", "true")
        except Exception:
            pass

        # Validate error envelope format before returning
        try:
            validate_error_envelope(shaped)
        except ValueError as e:
            log.error("Invalid error envelope format: %s", e)
            # Fallback to a safe envelope
            shaped = build_error(
                code="internal",
                message="Internal error",
                hint="try again shortly",
                meta={"original_error": str(e)},
            )
        _emit_auth_metrics(request, status, shaped)
        return JSONResponse(shaped, status_code=status, headers=headers)

    # Map generic HTTP errors to your stable envelope
    code, msg, hint = shape_from_status(status)
    if (
        isinstance(detail, str)
        and detail
        and detail not in {"Unauthorized", "forbidden", "Forbidden"}
    ):
        msg = detail

    details = _trace_details(request, status)
    _emit_auth_metrics(request, status, {"details": details})

    # Gentle backoff hints for 5xx
    if 500 <= status < 600:
        headers.setdefault("Retry-After", "1")

    # Ensure deprecated alias paths emit Deprecation header even when served by canonical handlers
    try:
        if request.url.path in {"/v1/whoami", "/v1/me", "/whoami", "/me"}:
            headers.setdefault("Deprecation", "true")
    except Exception:
        pass
    headers["X-Error-Code"] = code
    error_envelope = build_error(code=code, message=msg, hint=hint, meta=details)
    # Validation is redundant here since build_error always creates valid envelopes
    return JSONResponse(
        error_envelope,
        status_code=status,
        headers=headers,
    )


def _serialize_validation_errors(errors: list) -> list:
    """Convert Pydantic validation errors to JSON-serializable format."""
    import json

    def make_serializable(obj: Any) -> Any:
        """Convert non-serializable objects to strings."""
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    def serialize_error(error: dict) -> dict:
        """Recursively serialize a single error dict."""
        result = {}
        for key, value in error.items():
            if isinstance(value, dict):
                result[key] = serialize_error(value)
            elif isinstance(value, list):
                result[key] = [
                    (
                        serialize_error(item)
                        if isinstance(item, dict)
                        else make_serializable(item)
                    )
                    for item in value
                ]
            else:
                result[key] = make_serializable(value)
        return result

    return [serialize_error(error) for error in errors]


async def handle_validation_error(request: Request, exc: RequestValidationError):
    # Keep FastAPI-compatible shape *and* your envelope in one response.
    details_block = _trace_details(request, 422)
    # Serialize errors to ensure JSON compatibility
    serialized_errors = _serialize_validation_errors(exc.errors())

    # Use the canonical validation_error envelope so tests and clients
    # receive a consistent `validation_error` code and human-friendly message.
    envelope = build_error(
        code="validation_error",
        message="Validation Error",
        meta={**details_block, "errors": serialized_errors},
    )
    headers = {"X-Error-Code": "validation_error"}
    try:
        det = envelope.get("details") or {}
        if isinstance(det, dict):
            if det.get("error_id"):
                headers["X-Error-ID"] = str(det["error_id"])
            if det.get("trace_id"):
                headers["X-Trace-ID"] = str(det["trace_id"])
    except Exception:
        pass

    # Validate the envelope before returning
    try:
        validate_error_envelope(envelope)
    except ValueError as e:
        log.error("Invalid validation error envelope: %s", e)
        envelope = build_error(
            code="validation_error",
            message="Validation Error",
            meta={"original_error": str(e)},
        )

    # Include traditional FastAPI 'detail' for legacy clients/tests
    combined = {
        **envelope,
        "detail": "Validation Error",
        "errors": serialized_errors,
        "path": request.url.path,
        "method": request.method,
    }
    return JSONResponse(combined, status_code=422, headers=headers)


async def handle_unexpected_error(request: Request, exc: Exception):
    try:
        log.exception("unhandled.exception")
    except Exception:
        pass

    details = _trace_details(request, 500)
    env = build_error(
        code="internal",
        message="internal error",
        hint="try again shortly",
        meta=details,
    )
    # Validation is redundant here since build_error always creates valid envelopes
    headers = {"X-Error-Code": "internal"}
    try:
        det = env.get("meta") or {}  # Changed from details to meta
        if isinstance(det, dict):
            if det.get("error_id"):
                headers["X-Error-ID"] = str(det["error_id"])
            if det.get("trace_id"):
                headers["X-Trace-ID"] = str(det["trace_id"])
    except Exception:
        pass
    return JSONResponse(env, status_code=500, headers=headers)


def _emit_auth_metrics(request: Request, status: int, payload: dict[str, Any]):
    # Best-effort, never raise
    try:
        path = getattr(request.url, "path", "")
        from app.metrics import AUTH_401_TOTAL, AUTH_403_TOTAL

        if status == 401:
            hdr = request.headers.get("Authorization") or ""
            reason = "bad_token" if hdr.lower().startswith("bearer ") else "no_auth"
            AUTH_401_TOTAL.labels(route=path, reason=reason).inc()
        elif status == 403:
            scope = "unknown"
            det = payload.get("details") or {}
            if isinstance(det, dict):
                scope = det.get("scope") or scope
            AUTH_403_TOTAL.labels(route=path, scope=scope).inc()
    except Exception:
        pass


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    # Also handle pydantic ValidationError instances raised from code paths
    # that exercise model validation directly (not via FastAPI request parsing).
    app.add_exception_handler(PydanticValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
