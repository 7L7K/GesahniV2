import asyncio
import json
import os
import time
from threading import Thread

try:
    from redis import Redis
    from rq import Queue
except Exception:  # pragma: no cover - optional dependency
    Redis = None
    Queue = None

from .analytics import record_transcription
from .gpt_client import ask_gpt
from .memory.vector_store import add_user_memory
from .router import OPENAI_TIMEOUT_MS
from .session_manager import SESSIONS_DIR, extract_tags_from_text
from .session_store import SessionStatus, append_error
from .session_store import load_meta as _load_meta
from .session_store import save_meta as _save_meta
from .session_store import update_status
from .transcribe import transcribe_file as sync_transcribe_file


def _get_queue() -> Queue:
    if Redis is None or Queue is None:
        raise RuntimeError("redis/rq not installed")
    url = os.getenv("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL not configured")
    conn = Redis.from_url(url)
    return Queue("default", connection=conn)


def _chunk_text(text: str, size: int = 1024) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]


def enqueue_transcription(session_id: str, user_id: str | None = None) -> None:
    """Run transcription immediately when a task queue isn't available.

    The original implementation scheduled ``transcribe_task`` on the running
    event loop which meant API handlers returned before the work completed.
    Tests expect the transcription to finish synchronously so we execute the
    task in a background thread and block until it's done when Redis/RQ is not
    present.
    """

    update_status(session_id, SessionStatus.PROCESSING_WHISPER)
    if user_id is None:
        meta = _load_meta(session_id)
        user_id = meta.get("user_id", "anon")
    try:
        q = _get_queue()
        q.enqueue(transcribe_task, session_id, user_id)
    except Exception:
        thread = Thread(target=transcribe_task, args=(session_id, user_id))
        thread.start()
        thread.join()


def enqueue_tag_extraction(session_id: str) -> None:
    """Run tag extraction synchronously when no queue is configured."""

    update_status(session_id, SessionStatus.PROCESSING_GPT)
    try:
        q = _get_queue()
        q.enqueue(tag_task, session_id)
    except Exception:
        thread = Thread(target=tag_task, args=(session_id,))
        thread.start()
        thread.join()


def enqueue_summary(session_id: str) -> None:
    """Run summarization synchronously when the background queue is missing."""

    update_status(session_id, SessionStatus.PROCESSING_GPT)
    try:
        q = _get_queue()
        q.enqueue(summary_task, session_id)
    except Exception:
        thread = Thread(target=summary_task, args=(session_id,))
        thread.start()
        thread.join()


def transcribe_task(session_id: str, user_id: str) -> None:
    session_dir = SESSIONS_DIR / session_id
    audio_path = session_dir / "audio.wav"
    transcript_path = session_dir / "transcript.txt"
    start = time.monotonic()
    error = False
    try:
        text = sync_transcribe_file(str(audio_path))
        transcript_path.write_text(text, encoding="utf-8")
        for chunk in _chunk_text(text):
            try:
                add_user_memory(user_id, chunk)
            except Exception:
                pass
        # ensure session status reflects successful transcription
        update_status(session_id, SessionStatus.TRANSCRIBED)
    except Exception as e:  # pragma: no cover - network errors
        append_error(session_id, str(e))
        update_status(session_id, SessionStatus.ERROR)
        error = True
    duration = int((time.monotonic() - start) * 1000)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(record_transcription(duration, error=error))
    else:
        loop.create_task(record_transcription(duration, error=error))


def tag_task(session_id: str) -> None:
    session_dir = SESSIONS_DIR / session_id
    transcript_path = session_dir / "transcript.txt"
    tags_path = session_dir / "tags.json"
    meta = _load_meta(session_id)
    try:
        text = transcript_path.read_text(encoding="utf-8")
        tags = extract_tags_from_text(text)
        tags_path.write_text(
            json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8"
        )
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
        summary, _, _, _ = asyncio.run(
            ask_gpt(
                f"Summarize the following:\n{text}",
                timeout=OPENAI_TIMEOUT_MS / 1000,
                routing_decision=None,
            )
        )
        tags = extract_tags_from_text(text)
        summary_path.write_text(
            json.dumps({"summary": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # persist tags so subsequent searches can find this session
        tags_path.write_text(
            json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        meta = _load_meta(session_id)
        meta["tags"] = tags
        meta["status"] = SessionStatus.DONE.value
        _save_meta(session_id, meta)
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
