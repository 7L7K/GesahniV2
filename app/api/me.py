from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from ..deps.user import get_current_user_id, get_current_session_device
from ..config_runtime import get_config
from ..user_store import user_store


router = APIRouter(tags=["Auth"])


@router.get("/me")
async def me(user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    is_auth = user_id != "anon"
    stats = await user_store.get_stats(user_id) if is_auth else None

    cfg = get_config()
    flags = {
        "retrieval_pipeline": os.getenv("RETRIEVAL_PIPELINE", "0").lower() in {"1", "true", "yes"},
        "use_hosted_rerank": os.getenv("RETRIEVE_USE_HOSTED_CE", "0").lower() in {"1", "true", "yes"},
        "debug_model_routing": os.getenv("DEBUG_MODEL_ROUTING", "0").lower() in {"1", "true", "yes"},
        "ablation_flags": sorted(list(cfg.obs.ablation_flags)),
        "trace_sample_rate": cfg.obs.trace_sample_rate,
    }

    profile = {
        "user_id": user_id,
        "login_count": (stats or {}).get("login_count", 0),
        "last_login": (stats or {}).get("last_login"),
        "request_count": (stats or {}).get("request_count", 0),
    }
    return {"is_authenticated": is_auth, "profile": profile, "flags": flags}


@router.get("/whoami")
async def whoami(request: Request, user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    sess = get_current_session_device(request, None)
    scopes = []
    try:
        payload = getattr(request.state, "jwt_payload", None)
        raw_scopes = []
        if isinstance(payload, dict):
            raw_scopes = payload.get("scope") or payload.get("scopes") or []
            if isinstance(raw_scopes, str):
                scopes = [s.strip() for s in raw_scopes.split() if s.strip()]
            else:
                scopes = [str(s).strip() for s in raw_scopes if str(s).strip()]
    except Exception:
        scopes = []
    providers = []
    if os.getenv("PROVIDER_SPOTIFY", "").lower() in {"1","true","yes","on"}:
        providers.append("spotify")
    return {
        "is_authenticated": user_id != "anon",
        "user_id": user_id,
        "session_id": sess.get("session_id"),
        "device_id": sess.get("device_id"),
        "scopes": scopes,
        "providers": providers,
    }


__all__ = ["router"]


