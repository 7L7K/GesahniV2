from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
import io

from ..deps.user import get_current_user_id
from ..tts_orchestrator import synthesize


router = APIRouter(prefix="/tts", tags=["Music"])


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


class TTSAck(BaseModel):
    status: str = "ok"

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})


@router.post("/speak", response_model=TTSAck, responses={200: {"model": TTSAck}})
async def speak(req: TTSRequest, user_id: str = Depends(get_current_user_id)):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="empty_text")
    audio = await synthesize(
        text=req.text,
        mode=(req.mode or "utility"),
        intent_hint=req.intent,
        sensitivity_hint=req.sensitive,
        openai_voice=req.voice,
    )
    return StreamingResponse(io.BytesIO(audio), media_type="audio/wav")



