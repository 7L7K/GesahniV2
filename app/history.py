import os
import json
import asyncio
from datetime import datetime
import logging

from .logging_config import req_id_var

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "history.json")
_lock = asyncio.Lock()
logger = logging.getLogger(__name__)


def _write(record: dict) -> None:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []
    data.append(record)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


async def append_history(prompt: str, engine_used: str, response: str) -> None:
    record = {
        "req_id": req_id_var.get(),
        "prompt": prompt,
        "engine_used": engine_used,
        "response": response,
        "timestamp": datetime.utcnow().isoformat(),
    }
    async with _lock:
        try:
            await asyncio.to_thread(_write, record)
        except Exception as e:
            logger.exception("Failed to append history: %s", e)
