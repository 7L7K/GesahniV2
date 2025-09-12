from __future__ import annotations

import logging
from typing import Any

from .logging_config import req_id_var

try:  # best-effort import
    from .otel_utils import get_trace_id_hex
except Exception:  # pragma: no cover

    def get_trace_id_hex() -> str | None:  # type: ignore
        return None


def log_with_enhanced_schema(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    provider: str | None = None,
    service: str | None = None,
    sub: str | None = None,
    status_code: int | None = None,
    latency_ms: float | None = None,
    error_code: str | None = None,
    extra_meta: dict[str, Any] | None = None,
    **kwargs,
) -> None:
    """Log with enhanced structured schema including required fields.

    Ensures all logs include: provider, service, sub, req_id, trace_id,
    status_code, latency_ms, error_code where available.
    """
    req_id = req_id_var.get()
    trace_id = get_trace_id_hex()

    meta = {
        "req_id": req_id,
        "trace_id": trace_id,
    }

    # Add required structured fields
    if provider is not None:
        meta["provider"] = provider
    if service is not None:
        meta["service"] = service
    if sub is not None:
        meta["sub"] = sub
    if status_code is not None:
        meta["status_code"] = status_code
    if latency_ms is not None:
        meta["latency_ms"] = latency_ms
    if error_code is not None:
        meta["error_code"] = error_code

    # Add any additional meta
    if extra_meta:
        meta.update(extra_meta)

    # Remove None values to keep logs clean
    meta = {k: v for k, v in meta.items() if v is not None}

    logger.log(level, message, extra={"meta": meta}, **kwargs)


def log_request_start(
    logger: logging.Logger,
    method: str,
    path: str,
    *,
    user_id: str | None = None,
    provider: str | None = None,
    service: str | None = None,
    **kwargs,
) -> None:
    """Log the start of a request with enhanced schema."""
    log_with_enhanced_schema(
        logger,
        logging.INFO,
        f"Request started: {method} {path}",
        provider=provider,
        service=service,
        sub=user_id,
        extra_meta={
            "method": method,
            "path": path,
            "phase": "start",
        },
        **kwargs,
    )


def log_request_complete(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    latency_ms: float,
    *,
    user_id: str | None = None,
    provider: str | None = None,
    service: str | None = None,
    error_code: str | None = None,
    **kwargs,
) -> None:
    """Log the completion of a request with enhanced schema."""
    level = logging.ERROR if status_code >= 400 else logging.INFO

    log_with_enhanced_schema(
        logger,
        level,
        f"Request completed: {method} {path} -> {status_code}",
        provider=provider,
        service=service,
        sub=user_id,
        status_code=status_code,
        latency_ms=latency_ms,
        error_code=error_code,
        extra_meta={
            "method": method,
            "path": path,
            "phase": "complete",
        },
        **kwargs,
    )


def log_error(
    logger: logging.Logger,
    error: Exception,
    *,
    status_code: int | None = None,
    provider: str | None = None,
    service: str | None = None,
    sub: str | None = None,
    context: str | None = None,
    **kwargs,
) -> None:
    """Log an error with enhanced schema."""
    error_code = getattr(error, "code", None) or "unknown_error"

    log_with_enhanced_schema(
        logger,
        logging.ERROR,
        f"Error: {type(error).__name__}: {str(error)}",
        provider=provider,
        service=service,
        sub=sub,
        status_code=status_code,
        error_code=error_code,
        extra_meta={
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
        },
        **kwargs,
    )


def log_service_call(
    logger: logging.Logger,
    service: str,
    operation: str,
    *,
    provider: str | None = None,
    sub: str | None = None,
    latency_ms: float | None = None,
    status_code: int | None = None,
    error_code: str | None = None,
    **kwargs,
) -> None:
    """Log a service call with enhanced schema."""
    level = logging.ERROR if status_code and status_code >= 400 else logging.DEBUG

    log_with_enhanced_schema(
        logger,
        level,
        f"Service call: {service}.{operation}",
        provider=provider,
        service=service,
        sub=sub,
        latency_ms=latency_ms,
        status_code=status_code,
        error_code=error_code,
        extra_meta={
            "operation": operation,
        },
        **kwargs,
    )


# Convenience functions for common logging patterns
def log_auth_event(
    logger: logging.Logger,
    event: str,
    *,
    sub: str | None = None,
    status_code: int | None = None,
    error_code: str | None = None,
    **kwargs,
) -> None:
    """Log authentication events."""
    log_with_enhanced_schema(
        logger,
        logging.INFO,
        f"Auth event: {event}",
        provider="auth",
        service="authentication",
        sub=sub,
        status_code=status_code,
        error_code=error_code,
        extra_meta={
            "event": event,
        },
        **kwargs,
    )


def log_api_call(
    logger: logging.Logger,
    endpoint: str,
    method: str,
    *,
    sub: str | None = None,
    status_code: int | None = None,
    latency_ms: float | None = None,
    error_code: str | None = None,
    **kwargs,
) -> None:
    """Log API calls."""
    log_with_enhanced_schema(
        logger,
        logging.INFO,
        f"API call: {method} {endpoint}",
        provider="api",
        service="http",
        sub=sub,
        status_code=status_code,
        latency_ms=latency_ms,
        error_code=error_code,
        extra_meta={
            "endpoint": endpoint,
            "method": method,
        },
        **kwargs,
    )


__all__ = [
    "log_with_enhanced_schema",
    "log_request_start",
    "log_request_complete",
    "log_error",
    "log_service_call",
    "log_auth_event",
    "log_api_call",
]
