import os
import asyncio
import logging
import time
import json
from typing import Any, AsyncIterator, Dict, Optional, Union

import httpx
from tenacity import AsyncRetrying, stop_after_attempt, wait_random_exponential

from app.deps.scheduler import scheduler, start as scheduler_start
from app.logging_config import req_id_var
from app.http_utils import json_request, log_exceptions
from app.metrics import LLAMA_LATENCY, LLAMA_TOKENS

# Default to local Ollama if not provided
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

logger = logging.getLogger(__name__)

# Global health flag toggled by startup and periodic checks
LLAMA_HEALTHY: bool = True

# Circuit breaker state
llama_failures: int = 0
llama_last_failure_ts: float = 0.0
llama_circuit_open: bool = False

# Concurrency limit
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
            json={"model": OLLAMA_MODEL, "prompt": "ping", "stream": False},
            timeout=10.0,
        )
        if err or not isinstance(data, dict) or not data.get("response"):
            raise RuntimeError(err or "empty_response")
        LLAMA_HEALTHY = True
        logger.debug("Ollama generation successful")
    except Exception as e:
        LLAMA_HEALTHY = False
        logger.warning("Cannot generate with Ollama at %s – %s", OLLAMA_URL, e)


def _record_failure() -> None:
    """Update circuit breaker failure counters."""
    global llama_failures, llama_last_failure_ts, llama_circuit_open
    now = time.monotonic()
    if now - llama_last_failure_ts > 60:
        llama_failures = 1
    else:
        llama_failures += 1
    llama_last_failure_ts = now
    if llama_failures >= 3:
        llama_circuit_open = True


def _reset_failures() -> None:
    """Reset circuit breaker state after a successful call."""
    global llama_failures, llama_circuit_open
    llama_failures = 0
    llama_circuit_open = False


async def startup_check() -> None:
    """
    Verify Ollama config and kick off health checks.
    If OLLAMA_URL or OLLAMA_MODEL is missing, warn and skip.
    """
    missing = [
        name
        for name, val in {"OLLAMA_URL": OLLAMA_URL, "OLLAMA_MODEL": OLLAMA_MODEL}.items()
        if not val
    ]
    if missing:
        logger.warning(
            "OLLAMA startup skipped – missing env vars: %s",
            ", ".join(missing)
        )
        return

    # Initial health check (won’t crash on failure)
    await _check_and_set_flag()

    # Schedule periodic re-checks every 5 minutes
    scheduler.add_job(_check_and_set_flag, "interval", minutes=5)
    scheduler_start()


async def get_status() -> Dict[str, Any]:
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
    prompt: str,
    model: Optional[str] = None,
    timeout: float = 30.0,
    gen_opts: Optional[Dict[str, Any]] = None,
) -> Union[AsyncIterator[str], Dict[str, str]]:
    """
    Stream tokens from Ollama. Returns an async generator you can iterate over,
    or a dict with an "error" key on failure.
    """
    global LLAMA_HEALTHY

    # -- Model guard ------------------------------------------------------
    model = model or OLLAMA_MODEL
    if not model:
        LLAMA_HEALTHY = False
        return {"error": "model_not_set"}

    # -- Health ping ------------------------------------------------------
    try:
        _, err = await json_request(
            "POST",
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": "ping", "stream": False},
            timeout=timeout,
        )
        if err:
            LLAMA_HEALTHY = False
            return {"error": "timeout"}
    except Exception:
        LLAMA_HEALTHY = False
        return {"error": "timeout"}

    # -- Circuit breaker --------------------------------------------------
    now = time.monotonic()
    if llama_circuit_open:
        if now - llama_last_failure_ts > 120:
            _reset_failures()
        else:
            async def _open() -> AsyncIterator[str]:
                raise RuntimeError("llama_circuit_open")
                yield  # noqa: unreachable
            return _open()

    # -- Streaming generator ----------------------------------------------
    url = f"{OLLAMA_URL}/api/generate"
    options: Dict[str, Any] = {"num_ctx": 2048}
    if gen_opts:
        options.update(gen_opts)
    payload = {"model": model, "prompt": prompt, "stream": True, "options": options}

    async def _generator() -> AsyncIterator[str]:
        global LLAMA_HEALTHY
        prompt_tokens = 0
        completion_tokens = 0
        start_time = time.monotonic()

        retry = AsyncRetrying(
            wait=wait_random_exponential(min=1, max=4),
            stop=stop_after_attempt(3),
            reraise=True,
        )

        async for attempt in retry:
            with attempt:
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
                                    except Exception:
                                        continue
                                    token = data.get("response")
                                    if token:
                                        yield token
                                    if data.get("prompt_eval_count") is not None and prompt_tokens == 0:
                                        prompt_tokens = data.get("prompt_eval_count", 0)
                                    if data.get("eval_count") is not None:
                                        completion_tokens = data.get("eval_count", completion_tokens)
                                    if data.get("done"):
                                        break
                    # on success
                    LLAMA_HEALTHY = True
                    _reset_failures()
                    break
                except Exception as e:
                    LLAMA_HEALTHY = False
                    _record_failure()
                    logger.warning(
                        "Ollama request failed",
                        extra={"meta": {"req_id": req_id_var.get(), "error": str(e)}}
                    )
                    raise

        # Record Prometheus metrics
        LLAMA_TOKENS.labels(direction="prompt").inc(prompt_tokens)
        LLAMA_TOKENS.labels(direction="completion").inc(completion_tokens)
        LLAMA_LATENCY.observe((time.monotonic() - start_time) * 1000)

    # Return the async generator itself
    return _generator()
