import os
import time
from datetime import datetime, timezone
from datetime import time as dt_time

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.home_assistant import _request

from . import budget as _budget
from .analytics import cache_hit_rate, get_metrics
from .deps.scopes import docs_security_with
from .deps.user import get_current_user_id
from .llama_integration import get_status as llama_get_status
from .memory.api import get_store as _get_vector_store  # type: ignore
from .memory.chroma_store import ChromaVectorStore  # type: ignore
from .memory.memory_store import MemoryVectorStore
from .memory.vector_store.qdrant import get_stats as _q_stats  # type: ignore
from .tts_orchestrator import TTSSpend

router = APIRouter(
    tags=["Admin"], dependencies=[Depends(docs_security_with(["admin:write"]))]
)

# Public router for observability endpoints (no auth required)
public_router = APIRouter(tags=["Observability"])


def _admin_token() -> str | None:
    """Return current admin token from environment (evaluated dynamically)."""
    tok = os.getenv("ADMIN_TOKEN")
    # In pytest: only bypass when no explicit ADMIN_TOKEN is set
    if os.getenv("PYTEST_RUNNING", "").lower() in {"1", "true", "yes"}:
        return tok or None if tok else None
    return tok or None


@router.get("/health")
async def health(user_id: str = Depends(get_current_user_id)) -> dict:
    """Authenticated health snapshot for the UI.

    Combines core readiness (unauthenticated) with optional dependency checks
    into a simple schema consumed by the frontend:

    {
      status: 'ok' | 'degraded' | 'fail',
      timestamp: ISO8601,
      checks: { backend: 'ok', llama: 'ok'|'error'|'skipped', ha: 'ok'|'error'|'skipped', ... },
      metrics: { llama_hits, gpt_hits, cache_hit_rate }
    }
    """
    from .api.health import health_ready as _ready, health_deps as _deps  # lazy import
    import datetime

    # Gather readiness and dependency snapshots (unauthenticated endpoints)
    ready = await _ready()  # may be dict or JSONResponse
    deps = await _deps()  # may be dict or JSONResponse

    # Normalize potential Response objects into plain dicts for internal use
    import json
    from fastapi import Response

    def _normalize(resp):
        # If already a dict, return as-is
        if isinstance(resp, dict):
            return resp
        # If it's a Response/JSONResponse, try to parse the body
        try:
            if isinstance(resp, Response):
                body = getattr(resp, "body", None)
                if body is None:
                    # Some Response subclasses may store media/content
                    body = getattr(resp, "media", None) or getattr(resp, "content", None)
                if isinstance(body, (bytes, bytearray)):
                    return json.loads(body.decode())
                if isinstance(body, str):
                    return json.loads(body)
                if isinstance(body, dict):
                    return body
        except Exception:
            pass
        return {}

    ready = _normalize(ready)
    deps = _normalize(deps)

    # Build checks map starting with backend (always ok if we reached here)
    checks: dict[str, str] = {"backend": "ok"}

    # Map readiness components (healthy/unhealthy -> ok/error)
    comps = (ready or {}).get("components", {}) if isinstance(ready, dict) else {}
    for name, comp in comps.items():
        status = str(comp.get("status", "unhealthy"))
        checks[name] = "ok" if status == "healthy" else ("degraded" if status == "degraded" else "error")

    # Merge dependency checks (ok/error/skipped)
    dep_checks = (deps or {}).get("checks", {}) if isinstance(deps, dict) else {}
    for name, st in dep_checks.items():
        # Only add if not present from readiness
        checks.setdefault(name, str(st))

    # Overall status derived from readiness first, then deps
    if (ready or {}).get("status") == "fail":
        overall = "fail"
    elif (ready or {}).get("status") == "degraded" or (deps or {}).get("status") == "degraded":
        overall = "degraded"
    else:
        overall = "ok"

    # Lightweight metrics for visibility
    m = get_metrics()
    metrics = {
        "llama_hits": m.get("llama", 0),
        "gpt_hits": m.get("gpt", 0),
        "fallbacks": m.get("fallback", 0),
        "cache_hit_rate": cache_hit_rate(),
    }

    return {
        "status": overall,
        "timestamp": datetime.datetime.now(timezone.utc).isoformat() + "Z",
        "checks": checks,
        "metrics": metrics,
    }


@router.get("/healthz")
async def healthz(response: Response) -> dict:
    """Report backend and LLaMA health for probes."""
    response.headers["Cache-Control"] = "no-store"
    llama_status = "error"
    try:
        stat = await llama_get_status()
        llama_status = stat["status"]
    except Exception:
        llama_status = "error"
    return {"backend": "ok", "llama": llama_status}


@router.get("/rate_limit_status")
async def rate_limit_status(user_id: str = Depends(get_current_user_id)) -> dict:
    """Return current rate-limit backend configuration and health."""
    try:
        from .security import get_rate_limit_backend_status  # lazy import

        return await get_rate_limit_backend_status()
    except Exception:
        # In case security module is unavailable or raises, return minimal info
        return {"backend": "unknown", "enabled": False, "connected": False}


@router.get("/config")
async def config(
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    # Require admin token if set
    _tok = _admin_token()
    if _tok and token != _tok:
        raise HTTPException(status_code=403, detail="forbidden")
    # Never expose sensitive secrets
    SENSITIVE_PREFIXES = (
        "API_KEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "KEY",
        "PRIVATE",
        "WEBHOOK_SECRET",
    )
    out = {}
    for k, v in os.environ.items():
        if not k.isupper():
            continue
        redact = any(p in k for p in SENSITIVE_PREFIXES)
        out[k] = "***" if redact else v
    out.setdefault("SIM_THRESHOLD", os.getenv("SIM_THRESHOLD", "0.24"))
    out.setdefault("VECTOR_METRIC", "cosine (locked)")
    out.setdefault("RETRIEVE_POLICY", "keep if sim>=0.75 (dist<=0.25)")
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
        tts = TTSSpend.snapshot()
        return {**b, "near_cap": near_cap, "tts": tts}
    except Exception:
        return {
            "tokens_used": 0.0,
            "minutes_used": 0.0,
            "reply_len_target": "normal",
            "escalate_allowed": True,
            "near_cap": False,
            "tts": {
                "spent_usd": 0.0,
                "cap_usd": float(os.getenv("MONTHLY_TTS_CAP", "15") or 15),
                "ratio": 0.0,
                "near_cap": False,
                "blocked": False,
            },
        }


# Back-compat alias used by some frontends
@router.get("/status/budget")
async def budget_status_alias(user_id: str = Depends(get_current_user_id)) -> dict:
    return await budget_status(user_id)  # type: ignore[arg-type]


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
    # Quiet hours status
    try:
        q_enabled = os.getenv("QUIET_HOURS", "0").lower() in {"1", "true", "yes", "on"}
        start_s = os.getenv("QUIET_HOURS_START", "22:00")
        end_s = os.getenv("QUIET_HOURS_END", "07:00")

        def _parse(t: str) -> dt_time:
            hh, mm = (t or "0:0").split(":", 1)
            return dt_time(int(hh), int(mm))

        active = False
        if q_enabled:
            now = datetime.now().time()
            start_t = _parse(start_s)
            end_t = _parse(end_s)
            if start_t <= end_t:
                active = start_t <= now <= end_t
            else:
                # Crosses midnight
                active = now >= start_t or now <= end_t
        out["quiet_hours"] = {
            "enabled": q_enabled,
            "start": start_s,
            "end": end_s,
            "active": active,
        }
    except Exception:
        out["quiet_hours"] = {"enabled": False, "active": False}
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
        _vector_store_instance = _get_vector_store()
        if isinstance(_vector_store_instance, MemoryVectorStore):
            out["vector_backend"] = "memory"
        elif isinstance(_vector_store_instance, ChromaVectorStore):  # type: ignore
            out["vector_backend"] = "chroma"
        else:
            # Include dual/qdrant detection by name to improve visibility
            name = type(_vector_store_instance).__name__.lower()
            out["vector_backend"] = name
            if "dual" in name:
                try:
                    out["vector_dual"] = {"qdrant": _q_stats()}
                except Exception:
                    pass
        # Qdrant health: basic collection existence for cache:qa and mem:user
        try:
            if out.get("vector_backend", "").startswith("qdrant") or "dual" in str(
                out.get("vector_backend", "")
            ):
                out.setdefault("vector_health", {})
                try:
                    out["vector_health"]["qdrant_cache_qa"] = _q_stats(
                        os.getenv("QDRANT_QA_COLLECTION", "cache:qa")
                    )
                except Exception:
                    out["vector_health"]["qdrant_cache_qa"] = {"error": True}
        except Exception:
            pass
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
    out["dry_run"] = os.getenv("DEBUG_MODEL_ROUTING", "").lower() in {
        "1",
        "true",
        "yes",
    }

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


@public_router.get("/observability")
async def observability_metrics() -> dict:
    """Observability metrics for /v1/ask requests.

    Returns golden queries for monitoring:
    - p95 latency by backend
    - error rate by backend and error type
    """
    from .observability import get_ask_latency_p95_by_backend, get_ask_error_rate_by_backend, log_ask_observability_summary

    # Log summary for monitoring
    log_ask_observability_summary()

    return {
        "latency_p95_by_backend": get_ask_latency_p95_by_backend(),
        "error_rate_by_backend": get_ask_error_rate_by_backend(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": "Golden queries for ASK observability budgets"
    }


# Admin endpoints have moved to app.api.admin. This module intentionally
# does not expose /admin/* routes to avoid duplication/conflicts.
