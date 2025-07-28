import os
import json
import asyncio
from datetime import datetime
import logging

from .logging_config import req_id_var

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "history.jsonl")
_lock = asyncio.Lock()
logger = logging.getLogger(__name__)

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
            # Append one line per record (newline JSON)
            line = json.dumps(record, ensure_ascii=False)
            await asyncio.to_thread(
                lambda: open(HISTORY_FILE, "a", encoding="utf-8").write(line + "\n")
            )
        except Exception as e:
            logger.exception("Failed to append history: %s", e)
