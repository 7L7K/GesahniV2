from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, HTTPException

from ..deps.user import get_current_user_id, get_current_session_device
from ..sessions_store import sessions_store
from ..auth_store import ensure_tables as _ensure_auth, create_pat as _create_pat
import secrets
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


@router.get("/sessions")
async def sessions(user_id: str = Depends(get_current_user_id)) -> list[dict]:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    rows = await sessions_store.list_user_sessions(user_id)
    out: list[dict] = []
    current_sid = os.getenv("CURRENT_SESSION_ID")
    for i, r in enumerate(rows):
        out.append(
            {
                "session_id": r.get("sid"),
                "device_id": r.get("did"),
                "device_name": r.get("device_name"),
                "created_at": r.get("created_at"),
                "last_seen_at": r.get("last_seen"),
                "current": bool((current_sid and r.get("sid") == current_sid) or i == 0),
            }
        )
    return out


@router.post("/sessions/{sid}/revoke", status_code=204)
async def revoke_session(sid: str, user_id: str = Depends(get_current_user_id)) -> None:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    await sessions_store.revoke_family(sid)
    return None


@router.get("/pats")
async def list_pats(user_id: str = Depends(get_current_user_id)) -> list[dict]:
    # Storage not yet wired for listing; return empty list for contract shape
    return []


@router.post("/pats")
async def create_pat(body: Dict[str, Any], user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="Unauthorized")
    await _ensure_auth()
    name = str(body.get("name") or "")
    scopes = body.get("scopes") or []
    exp_at = body.get("exp_at")
    if not name or not isinstance(scopes, list):
        raise HTTPException(status_code=400, detail="invalid_request")
    pat_id = f"pat_{secrets.token_hex(4)}"
    token = f"pat_live_{secrets.token_urlsafe(24)}"
    token_hash = secrets.token_hex(16)
    await _create_pat(id=pat_id, user_id=user_id, name=name, token_hash=token_hash, scopes=scopes, exp_at=None)
    return {"id": pat_id, "token": token, "scopes": scopes, "exp_at": exp_at}


__all__ = ["router"]


