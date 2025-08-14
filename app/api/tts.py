from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
import io

from ..deps.user import get_current_user_id
from ..tts_orchestrator import synthesize


router = APIRouter(prefix="/tts", tags=["TTS"])


class TTSRequest(BaseModel):
    text: str
    mode: str | None = "utility"  # utility | capture
    intent: str | None = None
    sensitive: bool | None = None
    voice: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "Hello there!",
                "mode": "utility",
                "intent": "notify",
                "sensitive": False,
                "voice": "alloy",
            }
        }
    )


@router.post(
    "/speak",
    responses={
        200: {
            "content": {
                "audio/wav": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                        "description": "PCM WAV audio stream",
                    }
                }
            }
        }
    },
)
async def speak(req: TTSRequest, request: Request, user_id: str = Depends(get_current_user_id)):
    # CSRF header enforcement for cookie-auth flows
    try:
        if (request.cookies.get("access_token") or request.cookies.get("refresh_token")) and request.headers.get("X-CSRF") is None:
            raise HTTPException(status_code=400, detail="missing_csrf")
    except Exception:
        pass
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty_text")
    # Length/byte caps
    import os as _os
    max_chars = int((_os.getenv("TTS_MAX_CHARS", "800") or 800))
    if len(text) > max_chars:
        raise HTTPException(status_code=400, detail="text_too_long")

    # Chunk long inputs for sequential streaming
    def _chunks(s: str, limit: int = 240) -> list[str]:
        import re as _re
        parts = _re.split(r"(?<=[\.!?])\s+", s)
        out: list[str] = []
        cur = ""
        for p in parts:
            if len(cur) + len(p) + 1 <= limit:
                cur = (cur + " " + p).strip()
            else:
                if cur:
                    out.append(cur)
                cur = p
        if cur:
            out.append(cur)
        return out or [s]

    chunks = _chunks(text)

    async def _gen():
        for chunk in chunks:
            audio = await synthesize(
                text=chunk,
                mode=(req.mode or "utility"),
                intent_hint=req.intent,
                sensitivity_hint=req.sensitive,
                openai_voice=req.voice,
            )
            yield audio

    if len(chunks) == 1:
        audio = await synthesize(
            text=text,
            mode=(req.mode or "utility"),
            intent_hint=req.intent,
            sensitivity_hint=req.sensitive,
            openai_voice=req.voice,
        )
        return StreamingResponse(io.BytesIO(audio), media_type="audio/wav")
    # Multi-part stream: raw chunk bytes; client handles sequential playback
    return StreamingResponse(_gen(), media_type="application/octet-stream")



