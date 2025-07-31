import json
import os
import time
from pathlib import Path
from typing import Any

try:
    from redis import Redis
    from rq import Queue
except Exception:  # pragma: no cover - optional dependency
    Redis = None
    Queue = None

from .session_manager import (
    SESSIONS_DIR,
    _load_meta,
    _save_meta,
    extract_tags_from_text,
)
from .transcribe import transcribe_file as sync_transcribe_file
from .analytics import record_transcription


def _get_queue() -> Queue:
    if Redis is None or Queue is None:
        raise RuntimeError("redis/rq not installed")
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    conn = Redis.from_url(url)
    return Queue("default", connection=conn)


def enqueue_transcription(session_id: str) -> None:
    try:
        q = _get_queue()
        q.enqueue(transcribe_task, session_id)
    except Exception:
        transcribe_task(session_id)


def enqueue_tag_extraction(session_id: str) -> None:
    try:
        q = _get_queue()
        q.enqueue(tag_task, session_id)
    except Exception:
        tag_task(session_id)


def transcribe_task(session_id: str) -> None:
    session_dir = SESSIONS_DIR / session_id
    audio_path = session_dir / "audio.wav"
    transcript_path = session_dir / "transcript.txt"
    meta = _load_meta(session_id)
    start = time.monotonic()
    error = False
    try:
        text = sync_transcribe_file(str(audio_path))
        transcript_path.write_text(text, encoding="utf-8")
        meta["status"] = "transcribed"
    except Exception as e:  # pragma: no cover - network errors
        meta.setdefault("errors", []).append(str(e))
        meta["status"] = "error"
        error = True
    _save_meta(session_id, meta)
    duration = int((time.monotonic() - start) * 1000)
    try:
        import asyncio

        asyncio.run(record_transcription(duration, error=error))
    except RuntimeError:
        # already running loop
        asyncio.create_task(record_transcription(duration, error=error))


def tag_task(session_id: str) -> None:
    session_dir = SESSIONS_DIR / session_id
    transcript_path = session_dir / "transcript.txt"
    tags_path = session_dir / "tags.json"
    meta = _load_meta(session_id)
    try:
        text = transcript_path.read_text(encoding="utf-8")
        tags = extract_tags_from_text(text)
        tags_path.write_text(json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8")
        meta["tags"] = tags
        meta["status"] = "tagged"
    except Exception as e:  # pragma: no cover - nlp errors
        meta.setdefault("errors", []).append(str(e))
        meta["status"] = "error"
    _save_meta(session_id, meta)


__all__ = [
    "enqueue_transcription",
    "enqueue_tag_extraction",
    "transcribe_task",
    "tag_task",
]
