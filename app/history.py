import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
import logging

import aiofiles                                   # pip install aiofiles

from .logging_config import req_id_var

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
#   • Override with $HISTORY_FILE if you want a custom location.
#   • By default we write to   <repo‑root>/data/history.jsonl
#     (repo‑root = two dirs up from this file).
# --------------------------------------------------------------------------
_DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "history.jsonl"
)
HISTORY_FILE = Path(os.getenv("HISTORY_FILE", _DEFAULT_PATH))
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

_lock = asyncio.Lock()
logger = logging.getLogger(__name__)
# --------------------------------------------------------------------------


async def append_history(prompt: str, engine_used: str, response: str) -> None:
    """
    Append one newline‑delimited JSON object to HISTORY_FILE.
    Uses an asyncio lock + aiofiles so concurrent requests never clobber.
    """
    print("📝 append_history called! engine =", engine_used)
    print("📁 will write to:", HISTORY_FILE)

    record = {
        "req_id": req_id_var.get(),
        "prompt": prompt,
        "engine_used": engine_used,
        "response": response,
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    async with _lock:
        try:
            async with aiofiles.open(HISTORY_FILE, "a", encoding="utf-8") as f:
                await f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.debug("history_write_ok", extra={"meta": record})
        except Exception:
            logger.exception("Failed to append history")
