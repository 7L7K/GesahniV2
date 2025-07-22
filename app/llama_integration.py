import os
import asyncio
import logging
import httpx
import time
from typing import Any

from .logging_config import req_id_var

OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

if not OLLAMA_URL or not OLLAMA_MODEL:
    raise RuntimeError("Missing OLLAMA_URL or OLLAMA_MODEL")

logger = logging.getLogger(__name__)


async def startup_check() -> None:
    """Verify the configured model exists on the Ollama server."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_URL}/api/tags")
        resp.raise_for_status()
        tags = resp.json()
        text = str(tags)
        if OLLAMA_MODEL not in text:
            raise RuntimeError(f"Model {OLLAMA_MODEL} not available")


async def get_status() -> dict[str, Any]:
    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_URL}/api/tags")
        resp.raise_for_status()
    latency = int((time.monotonic() - start) * 1000)
    return {"status": "healthy", "latency_ms": latency}


async def ask_llama(prompt: str, model: str | None = None, timeout: float = 30.0) -> Any:
    model = model or OLLAMA_MODEL
    attempt = 0
    last_error = "http_error"
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
        except httpx.TimeoutException:
            last_error = "timeout"
            logger.exception(
                "Ollama timeout",
                extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}},
            )
            attempt += 1
            if attempt < 2:
                await asyncio.sleep(0.2 * attempt)
                continue
        except httpx.HTTPError:
            last_error = "http_error"
            logger.exception(
                "Ollama HTTP error",
                extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}},
            )
            attempt += 1
            if attempt < 2:
                await asyncio.sleep(0.2 * attempt)
                continue
        except Exception:
            last_error = "json_error"
            logger.exception(
                "Ollama JSON error",
                extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}},
            )
            attempt += 1
            if attempt < 2:
                await asyncio.sleep(0.2 * attempt)
                continue
    return {"error": last_error, "llm_used": model}
