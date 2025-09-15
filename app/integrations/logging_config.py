import os
from contextvars import ContextVar

# Exposed so other modules can set/request ids
req_id_var: ContextVar[str] = ContextVar("req_id", default="-")

# Lightweight in-process error ring buffer for admin dashboard
_ERRORS: list[dict[str, any]] = []
_MAX_ERRORS = 200


def get_trace_id_hex() -> str | None:
    """Get current trace ID for log correlation."""
    try:
        from .otel_utils import get_trace_id_hex

        return get_trace_id_hex()
    except Exception:
        return None


def configure_logging():
    """Configure logging for integrations."""
    import logging
    import sys

    logger = logging.getLogger("app.integrations")
    # Don't re-add handlers repeatedly in tests
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()))
    # Let logs propagate; no basicConfig here.
    logger.propagate = True
    return logger
