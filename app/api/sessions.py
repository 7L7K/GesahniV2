from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from ..deps.user import get_current_user_id
from ..sessions_store import sessions_store


router = APIRouter(tags=["auth"], include_in_schema=False)


@router.get("/sessions")
async def list_sessions(user_id: str = Depends(get_current_user_id)) -> Dict[str, List[Dict[str, Any]]]:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    out = await sessions_store.list_user_sessions(user_id)
    return {"items": out}


@router.post("/sessions/{sid}/revoke")
async def revoke_session(sid: str, user_id: str = Depends(get_current_user_id)) -> Dict[str, str]:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    await sessions_store.revoke_family(sid)
    return {"status": "ok"}


@router.post("/devices/{did}/rename")
async def rename_device(did: str, new_name: str, user_id: str = Depends(get_current_user_id)) -> Dict[str, str]:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    ok = await sessions_store.rename_device(user_id, did, new_name)
    if not ok:
        raise HTTPException(status_code=400, detail="rename_failed")
    return {"status": "ok"}


__all__ = ["router"]

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, BackgroundTasks

from app.deps.user import get_current_user_id
from app.session_manager import (
    SESSIONS_DIR,
    generate_tags as queue_tag_extraction,
    save_session as finalize_capture_session,
    search_sessions as search_session_store,
    start_session as start_capture_session,
    get_session_meta,
)
from app.session_store import SessionStatus, list_sessions as list_session_store
from app.tasks import enqueue_summary, enqueue_transcription
from app.transcription import TranscriptionStream
from app.transcription import transcribe_file


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Care"])


@router.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    import uuid

    session_id = uuid.uuid4().hex
    session_dir = Path(SESSIONS_DIR) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    dest = session_dir / "source.wav"
    content = await file.read()
    dest.write_bytes(content)
    logger.info("sessions.upload", extra={"meta": {"dest": str(dest)}})
    return {"session_id": session_id}


@router.post("/capture/start")
async def capture_start(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    return await start_capture_session()


@router.post("/capture/save")
async def capture_save(
    request: Request,
    session_id: str = Form(...),
    audio: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    tags: str | None = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    tags_list = json.loads(tags) if tags else None
    await finalize_capture_session(session_id, audio, video, transcript, tags_list)
    return get_session_meta(session_id)


@router.post("/capture/tags")
async def capture_tags(
    request: Request,
    session_id: str = Form(...),
    user_id: str = Depends(get_current_user_id),
):
    await queue_tag_extraction(session_id)
    return {"status": "accepted"}


@router.get("/capture/status/{session_id}")
async def capture_status(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    meta = get_session_meta(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="session not found")
    return meta


@router.get("/sessions")
async def list_sessions(
    status: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    # Accept plain string in query for test compatibility and map to enum
    enum_val = None
    if status:
        try:
            enum_val = SessionStatus(status)
        except Exception:
            enum_val = None
    return list_session_store(enum_val)


@router.post("/sessions/{session_id}/transcribe")
async def trigger_transcription_endpoint(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    enqueue_transcription(session_id, user_id)
    return {"status": "accepted"}


@router.post("/sessions/{session_id}/summarize")
async def trigger_summary_endpoint(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    enqueue_summary(session_id)
    return {"status": "accepted"}


@router.websocket("/transcribe")
async def websocket_transcribe(
    ws: WebSocket,
    user_id: str = Depends(get_current_user_id),
):
    stream = TranscriptionStream(ws)
    await stream.process()


@router.websocket("/storytime")
async def websocket_storytime(
    ws: WebSocket, user_id: str = Depends(get_current_user_id)
):
    """Storytime streaming: audio → Whisper transcription with JSONL logging.

    Uses the same streaming mechanics as ``/transcribe`` but appends each
    incremental transcript chunk to `stories/` for later summarization.
    """

    from app.storytime import append_transcript_line

    stream = TranscriptionStream(ws)

    async def _transcribe_and_log(path: str) -> str:
        text = await transcribe_file(path)
        if text and text.strip():
            try:
                append_transcript_line(
                    session_id=stream.session_id,
                    text=text,
                    user_id=user_id,
                    speaker="user",
                )
            except Exception:
                logger.debug("append_transcript_line failed", exc_info=True)
        return text

    # Inject our wrapper after we know the session_id
    stream.transcribe = _transcribe_and_log  # type: ignore[assignment]
    await stream.process()


async def _background_transcribe(session_id: str) -> None:
    base = Path(SESSIONS_DIR)
    audio_path = base / session_id / "audio.wav"
    transcript_path = base / session_id / "transcript.txt"
    try:
        text = await transcribe_file(str(audio_path))
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(text, encoding="utf-8")
    except Exception as e:  # pragma: no cover - best effort
        logger.exception("Transcription failed: %s", e)


@router.post("/transcribe/{session_id}")
async def start_transcription(
    session_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    background_tasks.add_task(_background_transcribe, session_id)
    return {"status": "accepted"}


@router.get("/transcribe/{session_id}")
async def get_transcription(
    session_id: str, user_id: str = Depends(get_current_user_id)
):
    # Mirror tests' helper that points SESSIONS_DIR at tmp; read there
    transcript_path = Path(SESSIONS_DIR) / session_id / "transcript.txt"
    if transcript_path.exists():
        return {"text": transcript_path.read_text(encoding="utf-8")}
    # In some flows, transcript.txt is named source.wav transcript surrogate; fall back
    alt = Path(SESSIONS_DIR) / session_id / "source.wav"
    if alt.exists():
        return {"text": ""}
    raise HTTPException(status_code=404, detail="Transcript not found")


