from __future__ import annotations
"""Storytime helpers: JSONL transcript logging and nightly summarization.

This module provides lightweight primitives to:
- Append streaming transcript lines into date-scoped JSONL files under a
  configurable ``STORIES_DIR``
- Run a simple nightly summarization job that batches lines into chunks,
  asks the LLM for short summaries, and stores those summaries as user
  memories for future recall via the vector store

All functionality degrades gracefully when optional dependencies (APScheduler)
are missing. The design avoids introducing new runtime requirements for tests.
"""


import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .gpt_client import ask_gpt
from .memory.vector_store import add_user_memory
from .redaction import redact_and_store
from .router import OPENAI_TIMEOUT_MS
from .token_utils import count_tokens

logger = logging.getLogger(__name__)


# Base directory for story transcripts (JSONL per day/session)
STORIES_DIR = Path(os.getenv("STORIES_DIR", Path(__file__).parent.parent / "stories"))
STORIES_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _story_path(session_id: str, *, when: datetime | None = None) -> Path:
    d = (when or datetime.now(UTC)).strftime("%Y-%m-%d")
    return STORIES_DIR / f"{d}-{session_id}.jsonl"


def append_transcript_line(
    *,
    session_id: str,
    text: str,
    user_id: str | None = None,
    speaker: str = "user",
    confidence: float | None = None,
) -> None:
    """Append a single JSON line to the story file for ``session_id``.

    Fields: ``ts``, ``session_id``, ``user_id``, ``speaker``, ``confidence``, ``text``.
    """

    # Redact and store mapping per session to keep transcripts safe at rest
    safe_text = redact_and_store("transcript", session_id, text)

    rec = {
        "ts": _utc_now_iso(),
        "session_id": session_id,
        "user_id": user_id or "anon",
        "speaker": speaker,
        "confidence": confidence,
        "text": safe_text,
    }
    path = _story_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    logger.debug("storytime append: %s", path.name)


@dataclass
class _Chunk:
    user_id: str
    session_id: str
    text: str


def _load_lines(path: Path) -> list[dict]:
    lines: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                try:
                    lines.append(json.loads(raw))
                except Exception:
                    continue
    except FileNotFoundError:
        return []
    return lines


def _chunk_story_lines(lines: list[dict], target_tokens: int = 800) -> list[_Chunk]:
    """Group consecutive lines into chunks around ``target_tokens``."""

    chunks: list[_Chunk] = []
    buf: list[str] = []
    session_id = (lines[0].get("session_id") if lines else "unknown") or "unknown"
    user_id = (lines[0].get("user_id") if lines else "anon") or "anon"
    for line in lines:
        txt = str(line.get("text") or "").strip()
        if not txt:
            continue
        if not buf:
            buf.append(txt)
            continue
        tentative = " ".join(buf + [txt])
        if count_tokens(tentative) > target_tokens:
            chunks.append(
                _Chunk(user_id=user_id, session_id=session_id, text=" ".join(buf))
            )
            buf = [txt]
        else:
            buf.append(txt)
    if buf:
        chunks.append(
            _Chunk(user_id=user_id, session_id=session_id, text=" ".join(buf))
        )
    return chunks


def _summarize_text_sync(text: str) -> str:
    """Summarize text synchronously via ask_gpt using asyncio.run."""

    prompt = (
        "Summarize the following conversation snippet into 2-3 concise bullet points, "
        "keeping dates/names if present.\n\n" + text
    )
    try:
        summary, _, _, _ = asyncio.run(
            ask_gpt(prompt, timeout=OPENAI_TIMEOUT_MS / 1000, routing_decision=None)
        )
    except Exception as e:
        logger.warning("storytime summarize failed: %s", e)
        return ""
    return (summary or "").strip()


def summarize_stories_once() -> int:
    """Summarize all story files for today and store summaries as memories.

    Returns number of summaries written.
    """

    written = 0
    for path in STORIES_DIR.glob("*.jsonl"):
        lines = _load_lines(path)
        if not lines:
            continue
        chunks = _chunk_story_lines(lines)
        for ch in chunks:
            summary = _summarize_text_sync(ch.text)
            if not summary:
                continue
            try:
                add_user_memory(ch.user_id, summary)
                written += 1
            except Exception:
                # Do not fail the whole job if vector store is unavailable
                logger.debug("add_user_memory failed for %s", ch.user_id, exc_info=True)
    logger.info("storytime.summarize", extra={"meta": {"written": written}})
    return written


def schedule_nightly_jobs() -> None:
    """Schedule the nightly summarization job when APScheduler is available."""

    try:
        from .deps import scheduler as sched_mod
    except Exception:
        logger.debug("scheduler module unavailable; skipping storytime jobs")
        return

    scheduler = getattr(sched_mod, "scheduler", None)
    if scheduler is None or not hasattr(scheduler, "add_job"):
        logger.debug("AsyncIOScheduler missing; cannot schedule storytime jobs")
        return

    # Start if not running
    try:
        sched_mod.start()
    except Exception:
        pass

    try:
        scheduler.add_job(
            summarize_stories_once,
            trigger="cron",
            hour=2,
            minute=0,
            id="storytime_summarize_nightly",
            replace_existing=True,
        )
        # Use structured logging style consistently
        logger.info(
            "storytime.schedule",
            extra={"meta": {"cron": "2:00", "job": "storytime_summarize_nightly"}},
        )
    except Exception:
        logger.debug("Failed to schedule storytime summarization", exc_info=True)


__all__ = [
    "STORIES_DIR",
    "append_transcript_line",
    "summarize_stories_once",
    "schedule_nightly_jobs",
]
