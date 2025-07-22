import os
import time
from fastapi import APIRouter, HTTPException

from .home_assistant import _request
from .llama_integration import get_status as llama_get_status
from .analytics import get_metrics

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/config")
async def config() -> dict:
    return {k: v for k, v in os.environ.items() if k.isupper()}


@router.get("/ha_status")
async def ha_status() -> dict:
    start = time.monotonic()
    try:
        await _request("GET", "/states")
        latency = int((time.monotonic() - start) * 1000)
        return {"status": "healthy", "latency_ms": latency}
    except Exception:
        raise HTTPException(status_code=500, detail="ha_error")


@router.get("/llama_status")
async def llama_status() -> dict:
    try:
        return await llama_get_status()
    except Exception:
        raise HTTPException(status_code=500, detail="llama_error")


@router.get("/status")
async def full_status() -> dict:
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
