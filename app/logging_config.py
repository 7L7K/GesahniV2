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
        # Attach current trace id when available for log-trace correlation
        try:
            from .otel_utils import get_trace_id_hex  # local import to avoid hard dep at import time

            tid = get_trace_id_hex()
            if tid:
                payload["trace_id"] = tid
        except Exception:
            pass
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

    # Enhanced debugging: Always show logs to stdout for debugging
    force_stdout = os.getenv("LOG_TO_STDOUT", "").lower() in {"1", "true", "yes", "on"}
    debug_mode = os.getenv("DEBUG_MODE", "").lower() in {"1", "true", "yes", "on"}
    verbose_logging = os.getenv("VERBOSE_LOGGING", "").lower() in {"1", "true", "yes", "on"}
    
    # Force DEBUG level if verbose logging is enabled
    if verbose_logging and level != "DEBUG":
        level = "DEBUG"
        logging.info("Verbose logging enabled - setting level to DEBUG")
    
    if force_stdout or debug_mode or verbose_logging:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logging.info(f"Logging enabled: level={level}, stdout={force_stdout}, debug_mode={debug_mode}, verbose={verbose_logging}")
    else:
        handler = logging.NullHandler()
        logging.info(f"Logging disabled: level={level}, stdout={force_stdout}, debug_mode={debug_mode}, verbose={verbose_logging}")

    root = logging.getLogger()
    root.handlers = [handler, _ErrorBufferHandler()]  # blow away default handlers, add buffer
    root.setLevel(level)
    root.filters = [RequestIdFilter()]

    # Enhanced logging for specific modules when in debug mode
    if level == "DEBUG" or verbose_logging:
        # Enable detailed logging for auth, API, and core modules
        for module in [
            "app.auth",
            "app.api",
            "app.security", 
            "app.middleware",
            "app.router",
            "app.memory",
            "app.vector_store",
            "app.llama_integration",
            "app.gpt_client",
            "app.transcription",
            "app.voice",
            "app.skills",
        ]:
            logging.getLogger(module).setLevel(logging.DEBUG)
        
        # Enable HTTP request/response logging
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logging.getLogger("httpcore").setLevel(logging.DEBUG)
        
        # Enable uvicorn access logs
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        
        logging.info("Debug logging enabled for core modules")
    else:
        # Reduce third-party verbosity unless LOG_LEVEL is DEBUG
        for noisy in (
            "httpx",
            "httpcore",
            "apscheduler",
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
            "passlib.handlers.bcrypt",
        ):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    # Quiet SQLite and SQL-related noise by default
    # This silences noisy logs coming from the stdlib sqlite3 module,
    # the async wrapper `aiosqlite`, and SQLAlchemy engine/pool logs.
    for sql_noisy in (
        "sqlite3",
        "aiosqlite",
        "sqlalchemy",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
    ):
        try:
            logging.getLogger(sql_noisy).setLevel(logging.WARNING)
        except Exception:
            # Best-effort: don't allow logging setup to fail
            pass

    # Additional targeted quieting for noisy network/connect logs
    try:
        logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
    except Exception:
        pass
    try:
        logging.getLogger("app.http_utils").setLevel(logging.WARNING)
    except Exception:
        pass


def get_last_errors(n: int = 50) -> List[Dict[str, Any]]:
    # Return newest-last list
    return _ERRORS[-n:]
