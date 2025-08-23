from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends

from app.deps.scopes import docs_security_with

router = APIRouter(
    tags=["Admin"], dependencies=[Depends(docs_security_with(["admin:write"]))]
)


def _parse_models_env(val: str | None) -> list[dict[str, Any]]:
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
async def list_models() -> dict[str, Any]:
    # Preferred: config-driven from env JSON
    models = _parse_models_env(os.getenv("MODELS_JSON"))
    if not models:
        # Fallback: construct from allowed envs
        gpt = [m for m in (os.getenv("ALLOWED_GPT_MODELS", "").split(",")) if m]
        llama = [m for m in (os.getenv("ALLOWED_LLAMA_MODELS", "").split(",")) if m]
        items: list[dict[str, Any]] = []
        # enrich GPT entries with pricing when available
        try:
            from app.gpt_client import MODEL_PRICING  # type: ignore
        except Exception:
            MODEL_PRICING = {}  # type: ignore
        for m in gpt:
            meta: dict[str, Any] = {"engine": "gpt", "name": m}
            price = MODEL_PRICING.get(m)
            if isinstance(price, dict):
                meta["pricing_per_1k_tokens"] = {
                    "input": price.get("in"),
                    "output": price.get("out"),
                }
            items.append(meta)
        for m in llama:
            items.append({"engine": "llama", "name": m, "pricing_per_1k_tokens": None})
        models = items
    # Add basic capabilities hints
    for it in models:
        if "capabilities" not in it:
            if it.get("engine") == "gpt":
                it["capabilities"] = ["reasoning", "tools", "json"]
            else:
                it["capabilities"] = ["local"]
    return {"items": models}


__all__ = ["router"]
