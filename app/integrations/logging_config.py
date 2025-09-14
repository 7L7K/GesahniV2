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

    # Set up basic logging
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
