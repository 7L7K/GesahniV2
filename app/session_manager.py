import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any, List

from fastapi import UploadFile, HTTPException

from .history import append_history
from .telemetry import LogRecord
from .analytics import record_session as analytics_record_session

# Base directory for session storage
SESSIONS_DIR = Path(os.getenv("SESSIONS_DIR", Path(__file__).parent.parent / "sessions"))
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "10485760"))  # 10MB
ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/mpeg", "audio/webm"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm"}


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id


def _meta_path(session_id: str) -> Path:
    return _session_path(session_id) / "meta.json"


def _load_meta(session_id: str) -> dict[str, Any]:
    mp = _meta_path(session_id)
    if mp.exists():
        return json.loads(mp.read_text(encoding="utf-8"))
    return {}


def get_session_meta(session_id: str) -> dict[str, Any]:
    return _load_meta(session_id)


def _save_meta(session_id: str, meta: dict[str, Any]) -> None:
    mp = _meta_path(session_id)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


async def start_session() -> dict[str, str]:
    """Create a new session folder and meta.json entry."""
    ts = datetime.utcnow().isoformat(timespec="seconds")
    session_id = ts.replace(":", "-")
    session_dir = _session_path(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "session_id": session_id,
        "status": "started",
        "created_at": ts + "Z",
        "errors": [],
    }
    _save_meta(session_id, meta)
    rec = LogRecord(req_id="session", session_id=session_id, prompt="session_start")
    await append_history(rec)
    await analytics_record_session()
    return {"session_id": session_id, "path": str(session_dir)}


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
    meta["status"] = "saving"
    _save_meta(session_id, meta)

    if audio is not None:
        if audio.content_type not in ALLOWED_AUDIO_TYPES:
            raise HTTPException(status_code=415, detail="unsupported audio type")
        data = await audio.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="audio too large")
        (session_dir / "audio.wav").write_bytes(data)
    if video is not None:
        if video.content_type not in ALLOWED_VIDEO_TYPES:
            raise HTTPException(status_code=415, detail="unsupported video type")
        data = await video.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="video too large")
        (session_dir / "video.mp4").write_bytes(data)
    if transcript is not None:
        (session_dir / "transcript.txt").write_text(transcript, encoding="utf-8")

    meta["status"] = "saved"
    _save_meta(session_id, meta)

    if transcript is None:
        from .tasks import enqueue_transcription
        enqueue_transcription(session_id)
    else:
        from .tasks import enqueue_tag_extraction
        enqueue_tag_extraction(session_id)


async def generate_tags(session_id: str) -> None:
    from .tasks import enqueue_tag_extraction

    enqueue_tag_extraction(session_id)


async def search_sessions(query: str) -> List[dict[str, Any]]:
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
            results.append({"session_id": sid, "score": score, "snippet": snippet})
    return results


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
    "extract_tags_from_text",
]
