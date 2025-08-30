from __future__ import annotations

import os

from fastapi import APIRouter, Depends, WebSocket

from app.deps.user import get_current_user_id
from app.transcription import TranscriptionStream

router = APIRouter(tags=["Care"])


def _ws_origin_allowed(ws: WebSocket) -> bool:
    try:
        origin = ws.headers.get("Origin")
        configured = list(getattr(ws.app.state, "allowed_origins", []))  # type: ignore[attr-defined]
        if not configured:
            _env = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000") or "http://localhost:3000"
            configured = [o.strip() for o in _env.split(",") if o.strip()]
        return (not origin) or (origin in configured)
    except Exception:
        return True


@router.websocket("/ws/transcribe")
async def websocket_transcribe(ws: WebSocket, user_id: str = Depends(get_current_user_id)):
    if not _ws_origin_allowed(ws):
        try:
            await ws.close(code=1008, reason="origin_not_allowed")
        except Exception:
            pass
        return
    await ws.accept(subprotocol="json.realtime.v1")
    stream = TranscriptionStream(ws)
    await stream.process()


@router.websocket("/ws/storytime")
async def websocket_storytime(ws: WebSocket, user_id: str = Depends(get_current_user_id)):
    if not _ws_origin_allowed(ws):
        try:
            await ws.close(code=1008, reason="origin_not_allowed")
        except Exception:
            pass
        return
    await ws.accept(subprotocol="json.realtime.v1")
    # Mirror behavior from sessions module: augment transcription pipeline
    from app.storytime import append_transcript_line
    from app.transcription import transcribe_file

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
                pass
        return text

    stream.transcribe = _transcribe_and_log  # type: ignore[assignment]
    await stream.process()


# Legacy aliases (keep working, hidden from docs)
@router.websocket("/transcribe")
async def _legacy_transcribe(ws: WebSocket, user_id: str = Depends(get_current_user_id)):
    await websocket_transcribe(ws, user_id)  # type: ignore[arg-type]


@router.websocket("/storytime")
async def _legacy_storytime(ws: WebSocket, user_id: str = Depends(get_current_user_id)):
    await websocket_storytime(ws, user_id)  # type: ignore[arg-type]


__all__ = ["router"]

