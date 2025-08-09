import logging
import json
import os
import sys
from datetime import datetime
from contextvars import ContextVar
from typing import List, Dict, Any

# Exposed so other modules can set/request ids
req_id_var: ContextVar[str] = ContextVar("req_id", default="-")

# Lightweight in-process error ring buffer for admin dashboard
_ERRORS: List[Dict[str, Any]] = []
_MAX_ERRORS = 200


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


class _ErrorBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - IO free
        try:
            if record.levelno < logging.ERROR:
                return
            item = {
                "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "level": record.levelname,
                "component": record.name,
                "msg": record.getMessage(),
            }
            _ERRORS.append(item)
            if len(_ERRORS) > _MAX_ERRORS:
                # keep newest
                del _ERRORS[: max(1, len(_ERRORS) - _MAX_ERRORS)]
        except Exception:
            pass


def configure_logging() -> None:
    """
    Call once at app startup.
    LOG_LEVEL env var controls verbosity (default INFO).
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler, _ErrorBufferHandler()]  # blow away default handlers, add buffer
    root.setLevel(level)
    root.filters = [RequestIdFilter()]

    # Reduce third-party verbosity unless LOG_LEVEL is DEBUG
    if level != "DEBUG":
        for noisy in ("httpx", "httpcore", "apscheduler"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def get_last_errors(n: int = 50) -> List[Dict[str, Any]]:
    # Return newest-last list
    return _ERRORS[-n:]
