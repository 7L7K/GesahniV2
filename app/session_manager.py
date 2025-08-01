import os
import json
import hashlib
import tarfile
import shutil
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List

from fastapi import UploadFile, HTTPException

from .history import append_history
from .telemetry import LogRecord
from .analytics import record_session as analytics_record_session
from .session_store import (
    SESSIONS_DIR,
    SessionStatus,
    session_path as _session_path,
    load_meta as _load_meta,
    save_meta as _save_meta,
    create_session,
    update_status,
    get_session as get_session_meta,
)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "10485760"))  # 10MB

# allow only the base MIME types (no codec params)
ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/mpeg", "audio/webm", "audio/mp4"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm"}

logger = logging.getLogger(__name__)


async def start_session() -> dict[str, str]:
    """Create a new session folder and meta.json entry."""
    meta = create_session()
    session_dir = _session_path(meta["session_id"])
    session_dir.mkdir(parents=True, exist_ok=True)
    rec = LogRecord(req_id="session", session_id=meta["session_id"], prompt="session_start")
    await append_history(rec)
    await analytics_record_session()
    return {"session_id": meta["session_id"], "path": str(session_dir)}


async def _save_upload_file(
    file: UploadFile, dest: Path, max_bytes: int | None = None
) -> str:
    hash = hashlib.sha256()
    total = 0
    with open(dest, "wb") as fh:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            hash.update(chunk)
            total += len(chunk)
            if max_bytes and total > max_bytes:
                fh.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="file too large")
            if total > 100 * 1024 * 1024:
                logger.info("upload_progress", extra={"meta": {"bytes": total}})
    await file.close()
    return hash.hexdigest()


def _base_type(content_type: str) -> str:
    """
    Strip any ';' params from a MIME type and lowercase.
    e.g. 'audio/webm; codecs=opus' -> 'audio/webm'
    """
    return content_type.split(";", 1)[0].strip().lower()


async def save_session(
    session_id: str,
    audio: UploadFile | None = None,
    video: UploadFile | None = None,
    transcript: str | None = None,
) -> None:
    """Persist provided media and queue jobs."""
    session_dir = _session_path(session_id)
    if not session_dir.exists():
        raise FileNotFoundError("session not found")
    meta = _load_meta(session_id)

    if audio is not None:
        base_audio = _base_type(audio.content_type)
        if base_audio not in ALLOWED_AUDIO_TYPES:
            raise HTTPException(status_code=415, detail=f"unsupported audio type '{audio.content_type}'")
        checksum = await _save_upload_file(
            audio, session_dir / "audio.wav", MAX_UPLOAD_BYTES
        )
        meta["audio_checksum"] = checksum

    if video is not None:
        base_video = _base_type(video.content_type)
        if base_video not in ALLOWED_VIDEO_TYPES:
            raise HTTPException(status_code=415, detail=f"unsupported video type '{video.content_type}'")
        checksum = await _save_upload_file(
            video, session_dir / "video.mp4", MAX_UPLOAD_BYTES
        )
        meta["video_checksum"] = checksum

    tags: List[str] = []
    if transcript is not None:
        (session_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
        meta["status"] = SessionStatus.TRANSCRIBED.value
    _save_meta(session_id, meta)

    record = {
        "type": "capture",
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "tags": tags,
        "path": str(session_dir.relative_to(SESSIONS_DIR.parent)),
    }
    await append_history(record)


async def generate_tags(session_id: str) -> None:
    from .tasks import enqueue_tag_extraction
    enqueue_tag_extraction(session_id)


async def search_sessions(
    query: str, sort: str = "recent", page: int = 1, limit: int = 10
) -> List[dict[str, Any]]:
    q = query.lower()
    results: List[dict[str, Any]] = []
    for sess_dir in SESSIONS_DIR.iterdir():
        if not sess_dir.is_dir():
            continue
        sid = sess_dir.name
        score = 0
        snippet: str | None = None
        tfile = sess_dir / "transcript.txt"
        if tfile.exists():
            raw = tfile.read_text(encoding="utf-8")
            text = raw.lower()
            idx = text.find(q)
            if idx != -1:
                score += 1
                start = max(idx - 20, 0)
                end = min(idx + 20, len(raw))
                snippet = raw[start:end]
        tagfile = sess_dir / "tags.json"
        if tagfile.exists():
            try:
                tags = json.loads(tagfile.read_text(encoding="utf-8"))
                if any(q in str(tag).lower() for tag in tags):
                    score += 2  # weight tag matches higher
            except Exception:
                pass
        if score:
            meta = _load_meta(sid)
            results.append(
                {
                    "session_id": sid,
                    "score": score,
                    "snippet": snippet,
                    "created_at": meta.get("created_at"),
                }
            )
    if sort == "recent":
        results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    else:
        results.sort(key=lambda r: r.get("score", 0), reverse=True)
    start = (page - 1) * limit
    end = start + limit
    return results[start:end]


def archive_old_sessions(days: int = 90) -> List[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    archived: List[str] = []
    archive_dir = SESSIONS_DIR / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    for sess_dir in SESSIONS_DIR.iterdir():
        if not sess_dir.is_dir() or sess_dir.name == "archive":
            continue
        meta = _load_meta(sess_dir.name)
        created_at = meta.get("created_at")
        if not created_at:
            continue
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            continue
        if created_dt < cutoff:
            archive_path = archive_dir / f"{sess_dir.name}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(sess_dir, arcname=sess_dir.name)
            shutil.rmtree(sess_dir)
            archived.append(str(archive_path))
    return archived


# helper for tag extraction -----------------------------------------------------

def extract_tags_from_text(text: str) -> List[str]:
    """Return a simple list of tags from text using spaCy if available."""
    try:  # spaCy is optional
        import spacy

        try:
            nlp = spacy.load("en_core_web_sm")
        except Exception:
            nlp = spacy.blank("en")
        doc = nlp(text)
        tokens = []
        for t in doc:
            if t.is_alpha and not t.is_stop:
                lemma = t.lemma_ if t.lemma_ else t.text
                tokens.append(lemma.lower())
    except Exception:
        tokens = [t.lower() for t in text.split() if t.isalpha()]
    return sorted(set(tokens))


__all__ = [
    "SESSIONS_DIR",
    "start_session",
    "save_session",
    "generate_tags",
    "search_sessions",
    "get_session_meta",
    "archive_old_sessions",
    "extract_tags_from_text",
]
