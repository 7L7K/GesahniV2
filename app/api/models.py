from __future__ import annotations

import os
import json
from typing import Any, Dict, List

from fastapi import APIRouter


router = APIRouter(tags=["models"])


def _parse_models_env(val: str | None) -> List[Dict[str, Any]]:
    if not val:
        return []
    try:
        data = json.loads(val)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    # Preferred: config-driven from env JSON
    models = _parse_models_env(os.getenv("MODELS_JSON"))
    if not models:
        # Fallback: construct from allowed envs
        gpt = [m for m in (os.getenv("ALLOWED_GPT_MODELS", "").split(",")) if m]
        llama = [m for m in (os.getenv("ALLOWED_LLAMA_MODELS", "").split(",")) if m]
        models = ([{"engine": "gpt", "name": m} for m in gpt] + [{"engine": "llama", "name": m} for m in llama])
    return {"items": models}


__all__ = ["router"]


