import os
import asyncio
import logging
import time
from typing import Any

import httpx  # noqa: F401  # exposed for monkeypatching in tests

from .deps.scheduler import scheduler, start as scheduler_start
from .logging_config import req_id_var
from .http_utils import json_request, log_exceptions

# Default to local Ollama if not provided
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

logger = logging.getLogger(__name__)

# Global health flag toggled by startup and periodic checks
LLAMA_HEALTHY: bool = False


@log_exceptions("llama")
async def _check_and_set_flag() -> None:
    """Attempt a tiny generation and update ``LLAMA_HEALTHY`` accordingly."""
    global LLAMA_HEALTHY
    try:
        data, err = await json_request(
            "POST",
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": "ping",
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=10.0,
        )
        if err or not isinstance(data, dict) or not data.get("response"):
            raise RuntimeError(err or "empty_response")
        LLAMA_HEALTHY = True
        logger.debug("Ollama generation successful")
    except Exception as e:
        LLAMA_HEALTHY = False
        logger.warning("Cannot generate with Ollama at %s – %s", OLLAMA_URL, e)


async def startup_check() -> None:
    """
    Verify Ollama config and kick off health checks.
    If OLLAMA_URL or OLLAMA_MODEL is missing, we warn and skip.
    """
    missing = [
        name
        for name, val in {
            "OLLAMA_URL": OLLAMA_URL,
            "OLLAMA_MODEL": OLLAMA_MODEL,
        }.items()
        if not val
    ]
    if missing:
        logger.warning(
            "OLLAMA startup skipped – missing env vars: %s", ", ".join(missing)
        )
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


@log_exceptions("llama")
async def ask_llama(
    prompt: str, model: str | None = None, timeout: float = 30.0
) -> Any:
    """
    Send a generate request to Ollama, with up to two retries on timeout/HTTP errors.
    Returns the Llama response string, or an error dict if both attempts fail.
    """
    global LLAMA_HEALTHY
    model = model or OLLAMA_MODEL
    if not model:
        logger.warning("ask_llama called without model")
        return {"error": "model_not_set"}

    attempt = 0
    error: dict[str, Any] | None = None

    while attempt < 2:
        data, err = await json_request(
            "POST",
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        if err is None and isinstance(data, dict):
            return data.get("response", "").strip()

        LLAMA_HEALTHY = False
        logger.warning(
            "Ollama request failed",
            extra={
                "meta": {"attempt": attempt, "req_id": req_id_var.get(), "error": err}
            },
        )
        mapped = {"network_error": "timeout"}
        error = {"error": mapped.get(err, err or "http_error"), "llm_used": model}

        attempt += 1
        if attempt < 2:
            await asyncio.sleep(0.2 * (attempt + 1))

    return error or {"error": "http_error", "llm_used": model}
