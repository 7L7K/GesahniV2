import logging
import json
import os
import sys
from datetime import datetime
from contextvars import ContextVar

# Exposed so other modules can set/request ids
req_id_var: ContextVar[str] = ContextVar("req_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "req_id": getattr(record, "req_id", req_id_var.get()),
            "level": record.levelname,
            "component": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "meta"):
            payload["meta"] = record.meta
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            # Fallback to plain message if payload has unserialisable types
            return payload.get("msg", "")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Propagate request id from context‑var into every log line
        record.req_id = req_id_var.get()
        return True


def configure_logging() -> None:
    """
    Call once at app startup.
    LOG_LEVEL env var controls verbosity (default INFO).
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]  # blow away default handlers
    root.setLevel(level)
    root.filters = [RequestIdFilter()]

    # Reduce third-party verbosity unless LOG_LEVEL is DEBUG
    if level != "DEBUG":
        for noisy in ("httpx", "httpcore", "apscheduler"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
