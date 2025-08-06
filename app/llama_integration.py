import os
import asyncio
import logging
import time
import json
from typing import Any, AsyncIterator

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
_MAX_STREAMS = int(os.getenv("LLAMA_MAX_STREAMS", "2"))
_sema = asyncio.Semaphore(_MAX_STREAMS)


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


async def ask_llama(
    prompt: str, model: str | None = None, timeout: float = 30.0
) -> AsyncIterator[str]:
    """Stream tokens from Ollama.

    The previous implementation returned the entire response after the request
    completed.  This version streams partial tokens as they arrive so callers
    can surface incremental output to clients.
    """

    global LLAMA_HEALTHY
    model = model or OLLAMA_MODEL
    if not model:
        logger.warning("ask_llama called without model")
        raise RuntimeError("model_not_set")

    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"num_ctx": 2048},
    }

    try:
        async with _sema:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except Exception:  # pragma: no cover - defensive
                            continue
                        token = data.get("response")
                        if token:
                            yield token
                        if data.get("done"):
                            break
        LLAMA_HEALTHY = True
    except Exception as e:
        LLAMA_HEALTHY = False
        logger.warning(
            "Ollama request failed",
            extra={"meta": {"req_id": req_id_var.get(), "error": str(e)}},
        )
        raise
