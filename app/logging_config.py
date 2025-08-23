import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import Any

# Exposed so other modules can set/request ids
req_id_var: ContextVar[str] = ContextVar("req_id", default="-")

# Lightweight in-process error ring buffer for admin dashboard
_ERRORS: list[dict[str, Any]] = []
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
            from .otel_utils import (
                get_trace_id_hex,  # local import to avoid hard dep at import time
            )

            tid = get_trace_id_hex()
            if tid:
                payload["trace_id"] = tid
        except Exception:
            pass
        # Add runtime/build metadata
        try:
            payload["env"] = os.getenv("ENV", "").strip()
        except Exception:
            pass
        try:
            payload["build_sha"] = os.getenv("BUILD_SHA") or os.getenv("GIT_COMMIT") or os.getenv("GIT_HASH") or ""
        except Exception:
            pass
        try:
            payload["version"] = os.getenv("APP_VERSION") or os.getenv("GIT_TAG") or os.getenv("VERSION") or ""
        except Exception:
            pass
        if hasattr(record, "meta"):
            payload["meta"] = record.meta
            # Expose any session_id present in structured meta for easy searching
            try:
                if isinstance(record.meta, dict) and record.meta.get("session_id"):
                    payload["session_id"] = record.meta.get("session_id")
            except Exception:
                pass
        else:
            # Try to pick up session_id from in-process telemetry record when available
            try:
                from .telemetry import log_record_var  # local import to avoid hard dep

                lr = log_record_var.get()
                if lr is not None and getattr(lr, "session_id", None):
                    payload["session_id"] = lr.session_id
            except Exception:
                pass
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            # Fallback to plain message if payload has unserialisable types
            return payload.get("msg", "")


class DebugBannerFormatter(logging.Formatter):
    """Formatter that adds emoji/debug banners for local development."""
    
    def __init__(self, use_banners: bool = True):
        super().__init__()
        self.use_banners = use_banners
        self._banners = {
            "DEBUG": "🔍",
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨",
        }
    
    def format(self, record: logging.LogRecord) -> str:
        if not self.use_banners:
            return super().format(record)
        
        # Demote banners to DEBUG-only when not in a dev environment
        try:
            env = os.getenv("ENV", "").strip().lower()
            if env not in {"dev", "development", "local"} and record.levelno >= logging.INFO:
                # suppress emoji banners in non-dev for INFO+ logs
                return super().format(record)
        except Exception:
            pass

        banner = self._banners.get(record.levelname, "📝")
        formatted = super().format(record)
        return f"{banner} {formatted}"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Propagate request id from context‑var into every log line
        record.req_id = req_id_var.get()
        return True


class HealthCheckFilter(logging.Filter):
    """Filter to mute health check access logs."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Check if this is a health check request
        if hasattr(record, 'path') and record.path:
            path = record.path
            if path.startswith('/healthz') or path.startswith('/health/'):
                return False
        elif hasattr(record, 'args') and record.args:
            # Try to extract path from log message or args
            msg = record.getMessage()
            if '/healthz' in msg or '/health/' in msg:
                return False
        return True


class CORSConfigFilter(logging.Filter):
    """Filter to mute CORS configuration banner spam in non-DEBUG mode."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Only show CORS config logs in DEBUG mode
        # Silence common CORS startup logs at INFO level unless DEBUG
        if record.levelno >= logging.INFO:
            msg = record.getMessage()
            if any(phrase in msg for phrase in [
                "CORS CONFIGURATION DEBUG",
                "CORS_ALLOW_ORIGINS",
                "CORS allow_credentials",
                "Final CORS configuration",
                "END CORS CONFIGURATION DEBUG"
            ]):
                return False
        return True


class VectorStoreWarningFilter(logging.Filter):
    """Filter to show vector store warnings only once, then mute."""
    
    _warned_messages = set()
    
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.WARNING:
            msg = record.getMessage()
            # Check for vector store related warnings
            if any(phrase in msg for phrase in [
                "vector store",
                "Vector store",
                "Chroma",
                "Qdrant",
                "EMBED_DIM",
                "embedder"
            ]):
                if msg in self._warned_messages:
                    return False  # Already warned, mute
                self._warned_messages.add(msg)
        return True


class OllamaHealthFilter(logging.Filter):
    """Filter to mute Ollama health checks in non-DEBUG mode."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Only show Ollama health check logs in DEBUG mode
        if record.levelno <= logging.INFO:
            msg = record.getMessage()
            if any(phrase in msg for phrase in [
                "Ollama health check",
                "Cannot generate with Ollama",
                "Ollama generation successful",
                "LLaMA startup",
                "OLLAMA startup"
            ]):
                return False
        return True


class CookieTTLFilter(logging.Filter):
    """Filter to replace cookie TTL and emoji narration with boolean flags."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        
        # Replace cookie TTL messages with simple boolean
        if "cookie TTL" in msg.lower() or "ttl=" in msg.lower():
            # Extract the boolean flag and log a simpler message
            if "ttl=" in msg:
                # Try to extract TTL value and convert to boolean
                try:
                    if "ttl=0" in msg or "ttl=false" in msg:
                        record.msg = "Cookie TTL: disabled"
                    else:
                        record.msg = "Cookie TTL: enabled"
                except:
                    pass
        
        # Replace emoji narration with simple boolean flags
        if any(emoji in msg for emoji in ["🔍", "ℹ️", "⚠️", "❌", "🚨", "📝"]):
            # Extract the actual message without emoji
            for emoji in ["🔍", "ℹ️", "⚠️", "❌", "🚨", "📝"]:
                if emoji in msg:
                    record.msg = msg.replace(emoji, "").strip()
                    break
        
        return True


class SecretCheckFilter(logging.Filter):
    """Filter to condense repeated secret checks into one line."""
    
    _secret_check_count = 0
    _last_secret_summary = None
    
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        
        # Check if this is a secret verification message
        if any(phrase in msg for phrase in [
            "SECRET USAGE VERIFICATION",
            "SECRET VERIFICATION",
            "Missing required secrets",
            "Secrets with security issues",
            "All critical secrets are properly configured"
        ]):
            self._secret_check_count += 1
            
            # Only log the first occurrence or if it's different from last time
            if self._secret_check_count == 1 or msg != self._last_secret_summary:
                self._last_secret_summary = msg
                return True
            else:
                return False
        
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
    DEBUG_BANNERS env var controls emoji/debug banners (default false).
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Enhanced debugging: Always show logs to stdout for debugging
    force_stdout = os.getenv("LOG_TO_STDOUT", "").lower() in {"1", "true", "yes", "on"}
    debug_mode = os.getenv("DEBUG_MODE", "").lower() in {"1", "true", "yes", "on"}
    verbose_logging = os.getenv("VERBOSE_LOGGING", "").lower() in {"1", "true", "yes", "on"}
    use_debug_banners = os.getenv("DEBUG_BANNERS", "").lower() in {"1", "true", "yes", "on"}

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level, logging.INFO))

    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add request ID filter to all loggers
    request_id_filter = RequestIdFilter()
    root_logger.addFilter(request_id_filter)

    # Add custom filters to mute specific log messages
    if level != "DEBUG":
        # Only apply filters in non-DEBUG mode
        root_logger.addFilter(CORSConfigFilter())
        root_logger.addFilter(VectorStoreWarningFilter())
        root_logger.addFilter(OllamaHealthFilter())
        root_logger.addFilter(CookieTTLFilter())
        root_logger.addFilter(SecretCheckFilter())

    # Configure formatter based on debug banners setting
    if use_debug_banners:
        formatter = DebugBannerFormatter(use_banners=True)
        json_formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        json_formatter = JsonFormatter()

    # Add console handler
    if force_stdout or debug_mode or verbose_logging:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        logging.info(f"Logging enabled: level={level}, stdout={force_stdout}, debug_mode={debug_mode}, verbose={verbose_logging}, banners={use_debug_banners}")
    else:
        # Production: JSON logging to stderr
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(json_formatter)
        root_logger.addHandler(stderr_handler)
        logging.info(f"Logging disabled: level={level}, stdout={force_stdout}, debug_mode={debug_mode}, verbose={verbose_logging}, banners={use_debug_banners}")

    # Add error buffer handler for admin dashboard
    error_handler = _ErrorBufferHandler()
    error_handler.setFormatter(json_formatter)
    root_logger.addHandler(error_handler)

    # Reduce third-party verbosity unless LOG_LEVEL is DEBUG
    if level != "DEBUG":
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_errors() -> list[dict[str, Any]]:
    """Return recent errors for admin dashboard."""
    return _ERRORS.copy()


def get_last_errors(n: int) -> list[dict[str, Any]]:
    """Compatibility helper: return last n errors (new name used by main)."""
    try:
        return _ERRORS[-int(n) :]
    except Exception:
        return _ERRORS.copy()


def clear_errors() -> None:
    """Clear the error buffer."""
    _ERRORS.clear()
