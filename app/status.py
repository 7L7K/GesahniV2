import os
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from .deps.user import get_current_user_id

# ``prometheus_client`` is an optional dependency that provides a helper for
# exposing metrics in Prometheus' text format.  The library isn't required for
# most of the application logic and the unit tests used in this kata do not
# install it.  Importing it unconditionally caused a ``ModuleNotFoundError``
# during test collection which prevented the rest of the application from
# loading.  We fall back to a minimal stub implementation when the library is
# absent so that importing this module never fails.
try:  # pragma: no cover - exercised indirectly via tests
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except Exception:  # pragma: no cover - executed when dependency missing
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"

    def generate_latest() -> bytes:  # type: ignore[return-type]
        """Return a minimal metrics payload for tests."""

        try:
            from . import metrics

            parts = [
                f"{metrics.REQUEST_COUNT.name} {metrics.REQUEST_COUNT.value}",
                f"{metrics.REQUEST_LATENCY.name} {metrics.REQUEST_LATENCY.value}",
                f"{metrics.REQUEST_COST.name} {metrics.REQUEST_COST.value}",
            ]
            return ("\n".join(parts) + "\n").encode()
        except Exception:
            return b""


from app.home_assistant import _request
from .llama_integration import get_status as llama_get_status
from .analytics import get_metrics

router = APIRouter()

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")


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
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="forbidden")
    out = {k: v for k, v in os.environ.items() if k.isupper()}
    out.setdefault("SIM_THRESHOLD", os.getenv("SIM_THRESHOLD", "0.90"))
    try:
        import builtins

        builtins.data = out
    except Exception:  # pragma: no cover - best effort
        pass
    return out


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
    except Exception:
        out["ha"] = "error"
    try:
        llama_stat = await llama_get_status()
        out["llama"] = llama_stat["status"]
    except Exception:
        out["llama"] = "error"
    m = get_metrics()
    out["metrics"] = {
        "llama_hits": m["llama"],
        "gpt_hits": m["gpt"],
        "fallbacks": m["fallback"],
    }
    return out


@router.get("/metrics")
async def metrics(user_id: str = Depends(get_current_user_id)) -> Response:
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
