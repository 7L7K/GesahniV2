from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

startup_errors: list[dict[str, Any]] = []
runtime_errors: list[dict[str, Any]] = []


def record_error(error: Exception, context: str = "unknown") -> None:
    """Record an error for monitoring and diagnostics."""
    error_info = {
        "timestamp": datetime.now(UTC).isoformat(),
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context,
        "traceback": "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        ),
    }
    runtime_errors.append(error_info)
    if len(runtime_errors) > 100:
        runtime_errors.pop(0)

    try:  # best-effort audit trail logging
        from app.audit_new import AuditEvent, append

        audit_event = AuditEvent(
            user_id="system",
            route=f"system.{context}",
            method="ERROR",
            status=500,
            action="system_error",
            meta={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context,
                "traceback": error_info["traceback"],
            },
        )
        append(audit_event)
    except Exception as audit_error:  # pragma: no cover - optional dependency
        logger.debug("Failed to write error to audit log: %s", audit_error)

    logger.error("Error in %s: %s", context, error, exc_info=True)


__all__ = ["record_error", "runtime_errors", "startup_errors"]
