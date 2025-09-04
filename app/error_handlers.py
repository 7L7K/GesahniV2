from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.error_envelope import build_error, shape_from_status
from app.otel_utils import get_trace_id_hex

log = logging.getLogger(__name__)

def _trace_details(request: Request, status: int) -> Dict[str, Any]:
    try:
        tid = get_trace_id_hex()
    except Exception:
        tid = None
    return {
        "status_code": status,
        "trace_id": tid,
        "path": request.url.path,
        "method": request.method,
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
                if det.get("error_id"): headers["X-Error-ID"] = str(det["error_id"])
                if det.get("trace_id"): headers["X-Trace-ID"] = str(det["trace_id"])
        except Exception:
            pass

        _emit_auth_metrics_if_ask(request, status, shaped)
        return JSONResponse(shaped, status_code=status, headers=headers)

    # Map generic HTTP errors to your stable envelope
    code, msg, hint = shape_from_status(status)
    if isinstance(detail, str) and detail and detail not in {"Unauthorized", "forbidden", "Forbidden"}:
        msg = detail

    details = _trace_details(request, status)
    _emit_auth_metrics_if_ask(request, status, {"details": details})

    # Gentle backoff hints for 5xx
    if 500 <= status < 600:
        headers.setdefault("Retry-After", "1")

    headers["X-Error-Code"] = code
    return JSONResponse(build_error(code=code, message=msg, hint=hint, details=details),
                        status_code=status, headers=headers)

async def handle_validation_error(request: Request, exc: RequestValidationError):
    # Keep FastAPI-compatible shape *and* your envelope in one response.
    details_block = _trace_details(request, 422)
    envelope = build_error(
        code="invalid_input",
        message="Validation error",
        details={**details_block, "errors": exc.errors()},
    )
    headers = {"X-Error-Code": "invalid_input"}
    try:
        det = envelope.get("details") or {}
        if isinstance(det, dict):
            if det.get("error_id"): headers["X-Error-ID"] = str(det["error_id"])
            if det.get("trace_id"): headers["X-Trace-ID"] = str(det["trace_id"])
    except Exception:
        pass

    # Include traditional FastAPI 'detail' for legacy clients/tests
    combined = {**envelope, "detail": "Validation error", "errors": exc.errors(),
                "path": request.url.path, "method": request.method}
    return JSONResponse(combined, status_code=422, headers=headers)

async def handle_unexpected_error(request: Request, exc: Exception):
    try:
        log.exception("unhandled.exception")
    except Exception:
        pass

    details = _trace_details(request, 500)
    env = build_error(code="internal", message="internal error", hint="try again shortly",
                      details=details)
    headers = {"X-Error-Code": "internal"}
    try:
        det = env.get("details") or {}
        if isinstance(det, dict):
            if det.get("error_id"): headers["X-Error-ID"] = str(det["error_id"])
            if det.get("trace_id"): headers["X-Trace-ID"] = str(det["trace_id"])
    except Exception:
        pass
    return JSONResponse(env, status_code=500, headers=headers)

def _emit_auth_metrics_if_ask(request: Request, status: int, payload: Dict[str, Any]):
    # Best-effort, never raise
    try:
        path = getattr(request.url, "path", "")
        if not path.startswith("/v1/ask"):
            return
        from app.metrics import AUTH_401_TOTAL, AUTH_403_TOTAL
        if status == 401:
            hdr = request.headers.get("Authorization") or ""
            reason = "bad_token" if hdr.lower().startswith("bearer ") else "no_auth"
            AUTH_401_TOTAL.labels(route="/v1/ask", reason=reason).inc()
        elif status == 403:
            scope = "unknown"
            det = payload.get("details") or {}
            if isinstance(det, dict):
                scope = det.get("scope") or scope
            AUTH_403_TOTAL.labels(route="/v1/ask", scope=scope).inc()
    except Exception:
        pass

def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)


