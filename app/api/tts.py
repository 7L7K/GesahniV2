from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

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
    message: str = "TTS request accepted"

    model_config = ConfigDict(
        title="TTSAck",
        json_schema_extra={
            "example": {
                "status": "ok",
                "message": "TTS request accepted",
            }
        },
    )


@router.post(
    "/speak",
    response_model=TTSAck,
    responses={
        200: {
            "description": "TTS audio generated successfully",
            "content": {
                "audio/wav": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                        "description": "PCM WAV audio stream",
                    }
                },
                "application/json": {"schema": {"$ref": "#/components/schemas/TTSAck"}},
            },
        }
    },
)
async def speak(
    req: TTSRequest, request: Request, user_id: str = Depends(get_current_user_id)
):
    # CSRF: uniform enforcement for mutating routes when globally enabled
    try:
        import os as _os

        if _os.getenv("CSRF_ENABLED", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            from app.csrf import _extract_csrf_header  # lazy import

            token_hdr, used_legacy, legacy_allowed = _extract_csrf_header(request)
            cookie = request.cookies.get("csrf_token") or ""
            if used_legacy and not legacy_allowed:
                from app.http_errors import http_error

                raise http_error(
                    code="missing_csrf", message="CSRF token required", status=400
                )
            if not token_hdr or not cookie or token_hdr != cookie:
                from app.http_errors import forbidden

                raise forbidden(code="invalid_csrf", message="invalid CSRF token")
    except HTTPException:
        raise
    except Exception:
        pass
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty_text")
    # Length/byte caps
    import os as _os

    max_chars = int(_os.getenv("TTS_MAX_CHARS", "800") or 800)
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
