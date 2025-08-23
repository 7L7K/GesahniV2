import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api._deps import deps_protected_http
from app.deps.user import get_current_user_id
from app.session_manager import SESSIONS_DIR
from app.transcription import transcribe_file

router = APIRouter(tags=["Care"], dependencies=deps_protected_http())
log = logging.getLogger(__name__)


async def _background_transcribe(session_id: str) -> None:
    base = Path(SESSIONS_DIR)
    audio_path = base / session_id / "audio.wav"
    transcript_path = base / session_id / "transcript.txt"
    try:
        text = await transcribe_file(str(audio_path))
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(text, encoding="utf-8")
    except Exception:
        log.exception("Transcription failed for %s", session_id)


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
    from pathlib import Path

    p = Path(SESSIONS_DIR) / session_id / "transcript.txt"
    if p.exists():
        return {"text": p.read_text(encoding="utf-8")}
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Transcript not found")
