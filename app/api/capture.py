from fastapi import APIRouter, Depends, Form, UploadFile

from app.api._deps import deps_protected_http
from app.deps.user import get_current_user_id
from app.session_store import SessionStatus
from app.session_store import list_sessions as list_session_store

router = APIRouter(tags=["Care"], dependencies=deps_protected_http())

@router.post("/capture/start")
async def capture_start(user_id: str = Depends(get_current_user_id)):
    from app.session_manager import start_session as _start_capture_session
    return await _start_capture_session()

@router.post("/capture/save")
async def capture_save(
    session_id: str = Form(...),
    audio: UploadFile | None = Form(None),
    video: UploadFile | None = Form(None),
    transcript: str | None = Form(None),
    tags: str | None = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    from app.session_manager import save_session as _save
    tags_list = None
    if tags:
        try:
            import json as _json
            tags_list = _json.loads(tags)
        except Exception:
            tags_list = None
    await _save(session_id, audio, video, transcript, tags_list)
    from app.session_manager import get_session_meta as _get_meta
    return _get_meta(session_id)

@router.post("/capture/tags")
async def capture_tags(session_id: str = Form(...), user_id: str = Depends(get_current_user_id)):
    from app.session_manager import generate_tags as _gen
    await _gen(session_id)
    return {"status": "accepted"}

@router.get("/capture/status/{session_id}")
async def capture_status(session_id: str, user_id: str = Depends(get_current_user_id)):
    from app.api.sessions import capture_status as _status
    return await _status(session_id, user_id)

@router.get("/capture/sessions")
async def list_sessions_capture(status: str | None = None, user_id: str = Depends(get_current_user_id)):
    enum_val = None
    if status:
        try:
            enum_val = SessionStatus(status)
        except Exception:
            enum_val = None
    return list_session_store(enum_val)

@router.get("/search/sessions")
async def search_sessions(q: str, sort: str = "recent", page: int = 1, limit: int = 10, user_id: str = Depends(get_current_user_id)):
    from app.api.sessions import search_session_store as _search
    return await _search(q, sort=sort, page=page, limit=limit)

@router.post("/sessions/{session_id}/transcribe")
async def trigger_transcription_endpoint(session_id: str, user_id: str = Depends(get_current_user_id)):
    from app.api.sessions import trigger_transcription_endpoint as _tt
    return await _tt(session_id, user_id)

@router.post("/sessions/{session_id}/summarize")
async def trigger_summary_endpoint(session_id: str, user_id: str = Depends(get_current_user_id)):
    from app.api.sessions import trigger_summary_endpoint as _ts
    return await _ts(session_id, user_id)
