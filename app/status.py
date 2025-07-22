import os
import time
from fastapi import APIRouter, HTTPException
from .analytics import get_metrics
from .home_assistant import verify_connection
from .llama_integration import llama_status

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.get("/config")
async def config():
    return {k: v for k, v in os.environ.items() if k.isupper()}

@router.get("/ha_status")
async def ha_status():
    start = time.perf_counter()
    try:
        await verify_connection()
        latency = int((time.perf_counter() - start) * 1000)
        return {"status": "healthy", "latency_ms": latency}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/llama_status")
async def llama_status_route():
    try:
        return await llama_status()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def overall_status():
    metrics = get_metrics()
    status = {
        "backend": "ok",
        "ha": "error",
        "llama": "error",
        "gpt_quota": "2k reqs left",
        "metrics": {
            "llama_hits": metrics["llama"],
            "gpt_hits": metrics["gpt"],
            "fallbacks": metrics["fallback"],
        },
    }
    try:
        await verify_connection()
        status["ha"] = "ok"
    except Exception:
        status["ha"] = "error"
    try:
        ls = await llama_status()
        status["llama"] = ls["status"]
    except Exception:
        status["llama"] = "error"
    return status
