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
            logger.exception("Ollama timeout", extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}})
            error = {"error": "timeout", "llm_used": model}
            attempt += 1
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        except httpx.HTTPError as e:
            logger.exception("Ollama HTTP error", extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}})
            error = {"error": "http_error", "llm_used": model}
            attempt += 1
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        except Exception:
            logger.exception("Ollama JSON error", extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}})
            error = {"error": "json_error", "llm_used": model}
            attempt += 1
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
    return error if error is not None else {"error": "http_error", "llm_used": model}
