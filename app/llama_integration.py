import os
import asyncio
import logging
import httpx
import time
from typing import Any

from .deps.scheduler import scheduler, start as scheduler_start

from .logging_config import req_id_var

OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

if not OLLAMA_URL or not OLLAMA_MODEL:
    raise RuntimeError("Missing OLLAMA_URL or OLLAMA_MODEL")

logger = logging.getLogger(__name__)

# Global health flag toggled by startup and periodic checks
LLAMA_HEALTHY: bool = False


async def _check_and_set_flag() -> None:
    """Ping Ollama and update ``LLAMA_HEALTHY`` accordingly."""
    global LLAMA_HEALTHY
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
        LLAMA_HEALTHY = True
    except Exception:
        LLAMA_HEALTHY = False
        raise


async def startup_check() -> None:
    """Verify the configured model exists on the Ollama server and start health checks."""
    await _check_and_set_flag()
    scheduler.add_job(_check_and_set_flag, "interval", minutes=5)
    scheduler_start()


async def get_status() -> dict[str, Any]:
    start = time.monotonic()
    await _check_and_set_flag()
    latency = int((time.monotonic() - start) * 1000)
    if LLAMA_HEALTHY:
        return {"status": "healthy", "latency_ms": latency}
    raise RuntimeError("llama_error")


async def ask_llama(prompt: str, model: str | None = None, timeout: float = 30.0) -> Any:
    global LLAMA_HEALTHY
    model = model or OLLAMA_MODEL
    attempt = 0
    error: dict[str, Any] | None = None
    while attempt < 2:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "").strip()
        except httpx.TimeoutException as e:
            LLAMA_HEALTHY = False
            logger.exception("Ollama timeout", extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}})
            error = {"error": "timeout", "llm_used": model}
            attempt += 1
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        except httpx.HTTPError as e:
            LLAMA_HEALTHY = False
            logger.exception("Ollama HTTP error", extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}})
            error = {"error": "http_error", "llm_used": model}
            attempt += 1
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        except Exception:
            LLAMA_HEALTHY = False
            logger.exception("Ollama JSON error", extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}})
            error = {"error": "json_error", "llm_used": model}
            attempt += 1
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
    return error if error is not None else {"error": "http_error", "llm_used": model}
