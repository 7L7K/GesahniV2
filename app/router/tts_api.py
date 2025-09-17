"""Compatibility wrappers for TTS endpoints.

These call into `app.api.tts` when available and return queued audio shapes.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi.responses import JSONResponse

from app.errors import json_error
from app.tts_orchestrator import synthesize


async def tts_speak(request) -> JSONResponse:
    try:
        data = await request.json()
    except Exception:
        data = {}
    text = (data or {}).get("text")
    if not text:
        return json_error(
            code="validation_error",
            message="Missing text",
            http_status=400,
            meta={"detail": "missing text"},
        )

    audio_id = uuid.uuid4().hex
    out_dir = Path("data/tts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{audio_id}.wav"

    async def _bg_job(t: str, path: Path):
        try:
            audio = await synthesize(text=t)
            try:
                path.write_bytes(bytes(audio))
            except Exception:
                pass
        except Exception:
            # best-effort: write empty file to mark completion
            try:
                path.write_bytes(b"")
            except Exception:
                pass

    # fire-and-forget background generation
    try:
        asyncio.create_task(_bg_job(text, out_path))
    except Exception:
        pass

    return JSONResponse({"audio_id": audio_id, "status": "pending"}, status_code=202)


async def get_tts_audio(audio_id: str):
    p = Path("data/tts") / f"{audio_id}.wav"
    if not p.exists():
        return json_error(
            code="not_found",
            message="Audio file not found",
            http_status=404,
            meta={"detail": "not_found"},
        )
    from fastapi.responses import FileResponse

    return FileResponse(p, media_type="audio/wav")


# Register read route under alias router so /v1/tts/{audio_id} is available
try:
    router.get("/tts/{audio_id}")(get_tts_audio)
except Exception:
    pass
