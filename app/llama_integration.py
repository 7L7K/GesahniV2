import os
import asyncio
import logging
import httpx
import time
from typing import Any

from .deps.scheduler import scheduler, start as scheduler_start
from .logging_config import req_id_var

# Default to local Ollama if not provided
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

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
            tags = resp.json()
            if OLLAMA_MODEL and OLLAMA_MODEL not in str(tags):
                logger.warning("Model %s missing on Ollama", OLLAMA_MODEL)
        LLAMA_HEALTHY = True
        logger.debug("Ollama is healthy")
    except Exception as e:
        LLAMA_HEALTHY = False
        logger.warning("Cannot reach Ollama at %s – %s", OLLAMA_URL, e)


async def startup_check() -> None:
    """
    Verify Ollama config and kick off health checks.
    If OLLAMA_URL or OLLAMA_MODEL is missing, we warn and skip.
    """
    missing = [
        name
        for name, val in {"OLLAMA_URL": OLLAMA_URL, "OLLAMA_MODEL": OLLAMA_MODEL}.items()
        if not val
    ]
    if missing:
        logger.warning("OLLAMA startup skipped – missing env vars: %s", ", ".join(missing))
        return

    # Initial health check (won’t crash on failure)
    await _check_and_set_flag()

    # Schedule periodic re-checks every 5 minutes
    scheduler.add_job(_check_and_set_flag, "interval", minutes=5)
    scheduler_start()


async def get_status() -> dict[str, Any]:
    """
    On-demand health endpoint. Re-checks Ollama before responding.
    Returns healthy status & latency_ms, or raises if still down.
    """
    start = time.monotonic()
    await _check_and_set_flag()
    latency = int((time.monotonic() - start) * 1000)
    if LLAMA_HEALTHY:
        return {"status": "healthy", "latency_ms": latency}
    raise RuntimeError("llama_error")


async def ask_llama(
    prompt: str, model: str | None = None, timeout: float = 30.0
) -> Any:
    """
    Send a generate request to Ollama, with up to two retries on timeout/HTTP errors.
    Returns the Llama response string, or an error dict if both attempts fail.
    """
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
            logger.exception(
                "Ollama timeout",
                extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}},
            )
            error = {"error": "timeout", "llm_used": model}

        except httpx.HTTPError as e:
            LLAMA_HEALTHY = False
            logger.exception(
                "Ollama HTTP error",
                extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}},
            )
            error = {"error": "http_error", "llm_used": model}

        except Exception as e:
            LLAMA_HEALTHY = False
            logger.exception(
                "Ollama JSON error",
                extra={"meta": {"attempt": attempt, "req_id": req_id_var.get()}},
            )
            error = {"error": "json_error", "llm_used": model}

        attempt += 1
        # exponential backoff-ish
        await asyncio.sleep(0.2 * (attempt + 1))

    # both attempts failed
    return error or {"error": "http_error", "llm_used": model}
