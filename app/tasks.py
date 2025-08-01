import json
import os
import time
import asyncio
from pathlib import Path
from typing import Any

try:
    from redis import Redis
    from rq import Queue
except Exception:  # pragma: no cover - optional dependency
    Redis = None
    Queue = None

from .session_manager import SESSIONS_DIR, extract_tags_from_text
from .session_store import (
    SessionStatus,
    load_meta as _load_meta,
    save_meta as _save_meta,
    update_status,
    append_error,
)
from .transcribe import transcribe_file as sync_transcribe_file
from .analytics import record_transcription
from .gpt_client import ask_gpt


def _get_queue() -> Queue:
    if Redis is None or Queue is None:
        raise RuntimeError("redis/rq not installed")
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    conn = Redis.from_url(url)
    return Queue("default", connection=conn)


def enqueue_transcription(session_id: str) -> None:
    update_status(session_id, SessionStatus.PROCESSING_WHISPER)
    try:
        q = _get_queue()
        q.enqueue(transcribe_task, session_id)
    except Exception:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(transcribe_task, session_id))
        except RuntimeError:
            transcribe_task(session_id)


def enqueue_tag_extraction(session_id: str) -> None:
    update_status(session_id, SessionStatus.PROCESSING_GPT)
    try:
        q = _get_queue()
        q.enqueue(tag_task, session_id)
    except Exception:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(tag_task, session_id))
        except RuntimeError:
            tag_task(session_id)


def enqueue_summary(session_id: str) -> None:
    update_status(session_id, SessionStatus.PROCESSING_GPT)
    try:
        q = _get_queue()
        q.enqueue(summary_task, session_id)
    except Exception:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(summary_task, session_id))
        except RuntimeError:
            summary_task(session_id)


def transcribe_task(session_id: str) -> None:
    session_dir = SESSIONS_DIR / session_id
    audio_path = session_dir / "audio.wav"
    transcript_path = session_dir / "transcript.txt"
    start = time.monotonic()
    error = False
    try:
        text = sync_transcribe_file(str(audio_path))
        transcript_path.write_text(text, encoding="utf-8")
        update_status(session_id, SessionStatus.TRANSCRIBED)
    except Exception as e:  # pragma: no cover - network errors
        append_error(session_id, str(e))
        update_status(session_id, SessionStatus.ERROR)
        error = True
    duration = int((time.monotonic() - start) * 1000)
    try:
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
        update_status(session_id, SessionStatus.DONE)
    except Exception as e:  # pragma: no cover - nlp errors
        append_error(session_id, str(e))
        update_status(session_id, SessionStatus.ERROR)
    _save_meta(session_id, meta)


def summary_task(session_id: str) -> None:
    session_dir = SESSIONS_DIR / session_id
    transcript_path = session_dir / "transcript.txt"
    summary_path = session_dir / "summary.json"
    tags_path = session_dir / "tags.json"
    try:
        text = transcript_path.read_text(encoding="utf-8")
        # simple prompt; tests may monkeypatch ask_gpt
        summary, *_ = asyncio.run(ask_gpt(f"Summarize the following:\n{text}"))
        tags = extract_tags_from_text(text)
        summary_path.write_text(
            json.dumps({"summary": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tags_path.write_text(json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = _load_meta(session_id)
        meta["tags"] = tags
        _save_meta(session_id, meta)
        update_status(session_id, SessionStatus.DONE)
    except Exception as e:  # pragma: no cover - network errors
        append_error(session_id, str(e))
        update_status(session_id, SessionStatus.ERROR)


__all__ = [
    "enqueue_transcription",
    "enqueue_tag_extraction",
    "enqueue_summary",
    "transcribe_task",
    "tag_task",
    "summary_task",
]
