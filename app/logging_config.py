import json
import logging
import os
from datetime import datetime
import contextvars

try:
    from .middleware import request_id_ctx
except Exception:
    request_id_ctx = contextvars.ContextVar("req_id", default=None)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "timestamp": datetime.utcnow().isoformat(),
            "req_id": getattr(record, "req_id", None) or request_id_ctx.get(),
            "level": record.levelname.lower(),
            "component": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "meta"):
            base["meta"] = record.meta
        return json.dumps(base)

def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(LOG_LEVEL)

setup_logging = configure_logging
