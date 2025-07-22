import asyncio
import json
import logging
import os
import time
from fastapi import APIRouter, HTTPException
import httpx
from .logging_config import configure_logging

configure_logging()

OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

if not OLLAMA_URL or not OLLAMA_MODEL:
    raise RuntimeError("OLLAMA_URL and OLLAMA_MODEL must be set")

router = APIRouter()
logger = logging.getLogger(__name__)

async def verify_model() -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_URL}/api/tags")
        resp.raise_for_status()
        tags = [m.get("name") for m in resp.json().get("models", [])]
        if OLLAMA_MODEL not in tags:
            raise RuntimeError(f"Model {OLLAMA_MODEL} not found")

@router.get("/llama_status")
async def llama_status():
    start = time.perf_counter()
    try:
        await verify_model()
        latency = int((time.perf_counter() - start) * 1000)
        return {"status": "healthy", "latency_ms": latency}
    except Exception as e:
        logger.exception("llama_status failed", extra={"meta": str(e)})
        raise HTTPException(status_code=500, detail="unhealthy")

async def ask_llama(prompt: str, model: str | None = None) -> str | dict:
    model = model or OLLAMA_MODEL
    backoffs = [0.2, 0.4]
    for delay in backoffs:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "").strip()
        except httpx.TimeoutException as e:
            logger.exception("timeout", extra={"meta": str(e)})
            await asyncio.sleep(delay)
            return {"error": "timeout", "llm_used": model}
        except httpx.HTTPError as e:
            logger.exception("http error", extra={"meta": str(e)})
            await asyncio.sleep(delay)
            return {"error": "http_error", "llm_used": model}
        except json.JSONDecodeError as e:
            logger.exception("json error", extra={"meta": str(e)})
            await asyncio.sleep(delay)
            return {"error": "json_error", "llm_used": model}
    return {"error": "http_error", "llm_used": model}
