import os
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from .decisions import get_recent as decisions_recent, get_explain as decisions_get
from .deps.user import get_current_user_id

from app.home_assistant import _request
from .llama_integration import get_status as llama_get_status
from .analytics import get_metrics, cache_hit_rate, get_top_skills
from .memory.api import _store as _vector_store_instance  # type: ignore
from .memory.memory_store import MemoryVectorStore
from .memory.chroma_store import ChromaVectorStore  # type: ignore
from . import budget as _budget
import os

router = APIRouter(tags=["status"])

def _admin_token() -> str | None:
    """Return current admin token from environment (evaluated dynamically)."""
    tok = os.getenv("ADMIN_TOKEN")
    return tok or None


@router.get("/health")
async def health(user_id: str = Depends(get_current_user_id)) -> dict:
    return {"status": "ok"}


@router.get("/healthz")
async def healthz(user_id: str = Depends(get_current_user_id)) -> dict:
    """Report backend and LLaMA health for probes."""
    llama_status = "error"
    try:
        stat = await llama_get_status()
        llama_status = stat["status"]
    except Exception:
        llama_status = "error"
    return {"backend": "ok", "llama": llama_status}


@router.get("/config")
async def config(
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    # If ADMIN_TOKEN is unset, allow local access for troubleshooting
    _tok = _admin_token()
    if _tok and token != _tok:
        raise HTTPException(status_code=403, detail="forbidden")
    out = {k: v for k, v in os.environ.items() if k.isupper()}
    out.setdefault("SIM_THRESHOLD", os.getenv("SIM_THRESHOLD", "0.24"))
    try:
        import builtins

        builtins.data = out
    except Exception:  # pragma: no cover - best effort
        pass
    return out


@router.get("/budget")
async def budget_status(user_id: str = Depends(get_current_user_id)) -> dict:
    try:
        b = _budget.get_budget_state(user_id)
        near_cap = b.get("reply_len_target") == "short"
        return {**b, "near_cap": near_cap}
    except Exception:
        return {"tokens_used": 0.0, "minutes_used": 0.0, "reply_len_target": "normal", "escalate_allowed": True, "near_cap": False}


@router.get("/ha_status")
async def ha_status(user_id: str = Depends(get_current_user_id)) -> dict:
    start = time.monotonic()
    try:
        await _request("GET", "/states")
        latency = int((time.monotonic() - start) * 1000)
        return {"status": "healthy", "latency_ms": latency}
    except Exception:
        raise HTTPException(status_code=500, detail="ha_error")


@router.get("/llama_status")
async def llama_status(user_id: str = Depends(get_current_user_id)) -> dict:
    """Report LLaMA health by attempting a minimal generation."""
    try:
        return await llama_get_status()
    except Exception:
        raise HTTPException(status_code=500, detail="llama_error")


@router.get("/status")
async def full_status(user_id: str = Depends(get_current_user_id)) -> dict:
    out = {
        "backend": "ok",
        "ha": "error",
        "llama": "error",
        "gpt_quota": "2k reqs left",
        "metrics": {},
    }
    try:
        await _request("GET", "/states")
        out["ha"] = "ok"
        out["ha_ok"] = True
    except Exception:
        out["ha"] = "error"
        out["ha_ok"] = False
    try:
        llama_stat = await llama_get_status()
        out["llama"] = llama_stat["status"]
        out["llama_circuit"] = False
    except Exception:
        out["llama"] = "error"
    m = get_metrics()
    out["metrics"] = {
        "llama_hits": m["llama"],
        "gpt_hits": m["gpt"],
        "fallbacks": m["fallback"],
        "cache_hit_rate": cache_hit_rate(),
    }
    # Extended status fields for platform visibility
    try:
        # LLaMA circuit breaker state
        from .llama_integration import llama_circuit_open as _circuit

        out["llama_circuit"] = bool(_circuit)
    except Exception:
        out["llama_circuit"] = False

    # Vector backend info
    try:
        if isinstance(_vector_store_instance, MemoryVectorStore):
            out["vector_backend"] = "memory"
        elif isinstance(_vector_store_instance, ChromaVectorStore):  # type: ignore
            out["vector_backend"] = "chroma"
        else:
            out["vector_backend"] = type(_vector_store_instance).__name__.lower()
        # Collections or counts
        try:
            cache_keys = getattr(_vector_store_instance.qa_cache, "keys", None)
            if callable(cache_keys):
                out["collections"] = {"qa_cache_keys": len(cache_keys())}
        except Exception:
            pass
    except Exception:
        out["vector_backend"] = "unknown"

    # Dry-run flag
    out["dry_run"] = os.getenv("DEBUG_MODEL_ROUTING", "").lower() in {"1", "true", "yes"}

    # Budget snapshot
    try:
        b = _budget.get_budget_state(user_id)
        out["budget_today"] = {
            "tokens": b.get("tokens_used", 0.0),
            "minutes": b.get("minutes_used", 0.0),
        }
        out["limits"] = {
            "max_tokens": int(os.getenv("DAILY_TOKEN_CAP", "200000")),
            "max_minutes": float(os.getenv("DAILY_MINUTES_CAP", "60")),
        }
    except Exception:
        out["budget_today"] = {"tokens": 0.0, "minutes": 0.0}
        out["limits"] = {"max_tokens": 0, "max_minutes": 0.0}
    return out


@router.get("/admin/metrics")
async def admin_metrics(token: str | None = Query(default=None), user_id: str = Depends(get_current_user_id)) -> dict:
    _tok = _admin_token()
    if _tok and token != _tok:
        raise HTTPException(status_code=403, detail="forbidden")
    m = get_metrics()
    return {
        "metrics": m,
        "cache_hit_rate": cache_hit_rate(),
        "top_skills": get_top_skills(10),
    }


@router.get("/admin/router/decisions")
async def admin_router_decisions(
    limit: int = Query(default=500, ge=1, le=1000),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    _tok = _admin_token()
    if _tok and token != _tok:
        raise HTTPException(status_code=403, detail="forbidden")
    return {"items": decisions_recent(limit)}


@router.get("/explain")
async def explain_decision(
    req_id: str,
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    _tok = _admin_token()
    if _tok and token != _tok:
        raise HTTPException(status_code=403, detail="forbidden")
    data = decisions_get(req_id)
    if not data:
        raise HTTPException(status_code=404, detail="not_found")
    return data
