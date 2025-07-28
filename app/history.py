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
    """Append a history record to ``HISTORY_FILE``.

    If the file extension is ``.json`` we maintain a JSON array for tests,
    otherwise we append newline-delimited JSON objects (``.jsonl`` default).
    A lock ensures concurrent writes don't clobber the file.
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
            file_path = Path(HISTORY_FILE)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if file_path.suffix == ".json":
                existing = []
                if file_path.exists():
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        existing = json.loads(content) if content else []
                existing.append(record)
                async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(existing, ensure_ascii=False))
            else:
                async with aiofiles.open(file_path, "a", encoding="utf-8") as f:
                    await f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.debug("history_write_ok", extra={"meta": record})
        except Exception:
            logger.exception("Failed to append history")
