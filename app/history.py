import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
import logging
from typing import Any

from .telemetry import LogRecord

import aiofiles  # pip install aiofiles

from .logging_config import req_id_var

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
#   • Override with $HISTORY_FILE if you want a custom location.
#   • By default we write to   <repo‑root>/data/history.jsonl
#     (repo‑root = two dirs up from this file).
# --------------------------------------------------------------------------
_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "history.jsonl"
HISTORY_FILE = Path(os.getenv("HISTORY_FILE", _DEFAULT_PATH))
HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

_lock = asyncio.Lock()
logger = logging.getLogger(__name__)
# --------------------------------------------------------------------------


async def append_history(
    record_or_prompt: LogRecord | str | dict[str, Any],
    engine_used: str | None = None,
    response: str | None = None,
) -> None:
    """Append a history record to ``HISTORY_FILE``.

    ``record_or_prompt`` may be a ``LogRecord`` instance or the legacy
    ``prompt`` string (with ``engine_used`` and ``response`` also supplied).
    The function writes newline-delimited JSON objects. Missing optional fields
    are omitted from the output.
    """
    if isinstance(record_or_prompt, dict):
        record = record_or_prompt
        if "timestamp" not in record:
            record["timestamp"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    else:
        if isinstance(record_or_prompt, LogRecord):
            rec = record_or_prompt
        else:
            rec = LogRecord(
                req_id=req_id_var.get(),
                prompt=record_or_prompt,
                engine_used=engine_used,
                response=response,
                timestamp=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            )
        if rec.timestamp is None:
            rec.timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        record = rec.model_dump(exclude_none=True)

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
