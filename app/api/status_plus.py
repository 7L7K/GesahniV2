from __future__ import annotations

import os
from fastapi import APIRouter, Depends
from app.deps.user import get_current_user_id

router = APIRouter(tags=["status"])


@router.get("/status/features")
async def features(user_id: str = Depends(get_current_user_id)):
    def _flag(name: str) -> bool:
        return os.getenv(name, "").lower() in {"1", "true", "yes"}

    return {
        "ha_enabled": bool(os.getenv("HOME_ASSISTANT_TOKEN")),
        "vector_store": (os.getenv("VECTOR_STORE") or "memory").lower(),
        "gpt_enabled": bool(os.getenv("OPENAI_API_KEY")),
        "llama_url": os.getenv("OLLAMA_URL", ""),
        "oauth_google": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "proactive": _flag("ENABLE_PROACTIVE_ENGINE"),
        "deterministic_router": _flag("DETERMINISTIC_ROUTER"),
    }


