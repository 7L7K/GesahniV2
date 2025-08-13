from __future__ import annotations

import os
from fastapi import APIRouter, Depends

from ..deps.user import get_current_user_id


router = APIRouter(prefix="/voices", tags=["tts"])


@router.get("/catalog")
async def catalog(user_id: str = Depends(get_current_user_id)) -> dict:
    # In production, fetch from OpenAI Voices list. For now, expose static labels.
    voices = [
        {"id": os.getenv("OPENAI_TTS_VOICE", "alloy"), "label": "Expressive (Alloy)", "tier": "mini_tts|tts1|tts1_hd"},
        {"id": "verse", "label": "Rich HD (Verse)", "tier": "tts1_hd"},
        {"id": "aria", "label": "Expressive (Aria)", "tier": "tts1|tts1_hd"},
    ]
    return {"openai": voices, "piper": [{"id": os.getenv("PIPER_VOICE", "en_US-amy-low"), "label": "Local Piper"}]}



