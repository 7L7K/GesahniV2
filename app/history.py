import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles  # pip install aiofiles

from .logging_config import req_id_var
from .telemetry import LogRecord

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
            record["timestamp"] = (
                datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            )
    else:
        if isinstance(record_or_prompt, LogRecord):
            rec = record_or_prompt
        else:
            rec = LogRecord(
                req_id=req_id_var.get(),
                prompt=record_or_prompt,
                engine_used=engine_used,
                response=response,
                timestamp=(
                    datetime.now(UTC)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                ),
            )
        if rec.timestamp is None:
            rec.timestamp = (
                datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            )
        record = rec.model_dump(exclude_none=True)

    # ------------------------------------------------------------------
    # PHI/PII scrubber unless explicitly allowed
    # ------------------------------------------------------------------
    try:
        allow_phi = os.getenv("ALLOW_PHI_STORAGE", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if not allow_phi:
            import re

            def _redact(text: str) -> str:
                if not isinstance(text, str):
                    return text
                t = text
                # SSN (simple US pattern)
                t = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-SSN]", t)
                # Emails
                t = re.sub(
                    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                    "[REDACTED-EMAIL]",
                    t,
                )
                # Phone numbers (loose) e.g. +1 555-123-4567, (555) 123-4567, 5551234567
                t = re.sub(
                    r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?)?\d{3}[\s-]?\d{4}(?!\d)",
                    "[REDACTED-PHONE]",
                    t,
                )
                return t

            for key in ("prompt", "response"):
                if key in record and isinstance(record[key], str):
                    record[key] = _redact(record[key])
    except Exception:  # pragma: no cover - best effort
        pass

    async with _lock:
        try:
            file_path = Path(HISTORY_FILE)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if file_path.suffix == ".json":
                existing = []
                if file_path.exists():
                    async with aiofiles.open(file_path, encoding="utf-8") as f:
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


async def get_record_by_req_id(req_id: str) -> dict[str, Any] | None:
    """Return the most recent history record with the given request id.

    Supports both JSONL (newline-delimited objects) and a single JSON array file.
    Returns None when not found or on read/parse errors.
    """
    try:
        file_path = Path(HISTORY_FILE)
        if not file_path.exists():
            return None
        text = file_path.read_text(encoding="utf-8")
        if not text:
            return None
        # JSON array file
        if file_path.suffix == ".json":
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    for obj in reversed(data):
                        if isinstance(obj, dict) and obj.get("req_id") == req_id:
                            return obj
                return None
            except Exception:
                return None
        # JSONL file
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("req_id") == req_id:
                return obj
        return None
    except Exception:
        return None
