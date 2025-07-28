import os
import json
import asyncio
from datetime import datetime
import logging

from .logging_config import req_id_var   # whatever you’re using to stash req-ids

# ---------- configuration ----------
# history.jsonl will live one level *above* this file, i.e. <project-root>/history.jsonl
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "history.jsonl")

_lock = asyncio.Lock()
logger = logging.getLogger(__name__)
# -----------------------------------

async def append_history(prompt: str, engine_used: str, response: str) -> None:
    """
    Append a single JSON-line to HISTORY_FILE.
    The file is newline-delimited JSON so it can be tailed / grepped easily.
    Safe for concurrent async calls thanks to `_lock`.
    """
    record = {
        "req_id": req_id_var.get(),
        "prompt": prompt,
        "engine_used": engine_used,
        "response": response,
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
    }

    async with _lock:
        try:
            line = json.dumps(record, ensure_ascii=False)
            # do the write in a thread so we don’t block the event-loop
            await asyncio.to_thread(
                lambda: open(HISTORY_FILE, "a", encoding="utf-8").write(line + "\n")
            )
            logger.debug("history_write_ok", extra={"meta": record})
        except Exception as e:
            logger.exception("Failed to append history", exc_info=e)
