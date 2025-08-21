"""Thin wrapper around the OpenAI chat API.

The original project depended on the official ``openai`` package.  The
execution environment for the kata purposely omits this optional dependency so
that the tests can run without network access.  Importing the module
unconditionally would therefore raise a ``ModuleNotFoundError`` during test
collection which prevented the rest of the application from loading.

To keep the surface area of the module intact we attempt to import
``AsyncOpenAI`` and fall back to a tiny stub that simply raises a helpful error
when used.  Tests monkey‑patch ``ask_gpt`` so the stub is never exercised, but
the import no longer fails when the dependency is missing.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from collections.abc import Awaitable, Callable, AsyncIterator
import asyncio
from typing import TYPE_CHECKING

try:  # pragma: no cover - exercised indirectly
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - import-time guard

    class AsyncOpenAI:  # type: ignore
        """Fallback stub when ``openai`` isn't installed."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("openai package not installed")


from .metrics import (
    REQUEST_COST,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    MODEL_LATENCY_SECONDS,
)
from .model_params import for_openai
from .telemetry import log_record_var
from .otel_utils import start_span
from .model_config import (
    GPT_BASELINE_MODEL,
    GPT_MID_MODEL,
    GPT_HEAVY_MODEL,
)

if TYPE_CHECKING:  # pragma: no cover - only for type checkers
    from openai import AsyncOpenAI


OPENAI_MODEL = os.getenv("OPENAI_MODEL", GPT_MID_MODEL)

# Map internal router aliases to real OpenAI model ids.
# These aliases are used by the deterministic router and tests but may not
# correspond to public API model names. Normalize them here so the OpenAI
# client always receives a valid model identifier.
def _load_models_aliases() -> dict:
    aliases = {
        # Baseline lightweight models / aliases
        "gpt-5-nano": GPT_BASELINE_MODEL,
        "gpt-4.1-nano": GPT_MID_MODEL,
        # Mid-tier chat quality
        "gpt-5-mini": GPT_MID_MODEL,
        # Reasoning burst
        "o1-mini": os.getenv("GPT_REASONING_MODEL", "o1-mini"),
        # Heavy model alias
        GPT_HEAVY_MODEL: GPT_HEAVY_MODEL,
    }
    # Optional: supplement/override from MODELS_JSON
    try:
        raw = os.getenv("MODELS_JSON", "").strip()
        if raw:
            import json as _json
            data = _json.loads(raw)
            # Accept either a list of {alias: real} or a dict
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, str) and k and v:
                        aliases[k] = v
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            if isinstance(k, str) and isinstance(v, str) and k and v:
                                aliases[k] = v
    except Exception:
        pass
    return aliases

_MODEL_ALIASES = _load_models_aliases()


def _normalize_model_name(name: str | None) -> str:
    base = (name or OPENAI_MODEL).strip()
    return _MODEL_ALIASES.get(base, base)


def _load_default_system_prompt() -> str:
    """Load the default system prompt from prompts/system_default.txt.

    Falls back to a compact, hard-coded persona when the file is missing.
    """
    try:
        path = Path(__file__).parent / "prompts" / "system_default.txt"
        text = path.read_text(encoding="utf-8").strip()
        return (
            text
            or "You are Gesahni — a concise personal AI teammate. Be brief. Bullets over paragraphs. Ask at most one clarifying question."
        )
    except Exception:
        return (
            "You are Gesahni — a concise personal AI teammate. Be brief. "
            "Bullets over paragraphs. Ask at most one clarifying question."
        )


# Temporary system prompt to prime the assistant. Prefer env override, else file.
_ENV_SYSTEM = os.getenv("GPT_SYSTEM_PROMPT", "").strip()
SYSTEM_PROMPT = _ENV_SYSTEM if _ENV_SYSTEM else _load_default_system_prompt()

logger = logging.getLogger(__name__)
_client: AsyncOpenAI | None = None

# price in USD per 1k tokens (OpenAI pricing as of 2024-07-18)
# Separate rates for input and output tokens
# Source: https://openai.com/pricing
MODEL_PRICING = {
    "gpt-4o": {"in": 0.005, "out": 0.015},
    "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
    "gpt-5-mini": {"in": 0.00025, "out": 0.00025},
    "o1-mini": {"in": 0.0020, "out": 0.0020},  # approx
    "o4-mini": {"in": 0.0015, "out": 0.0015},  # internal accounting
    "gpt-4": {"in": 0.03, "out": 0.06},
    "gpt-3.5-turbo": {"in": 0.0005, "out": 0.0015},
    "gpt-3.5-turbo-instruct": {"in": 0.0015, "out": 0.0015},
}


def get_client() -> AsyncOpenAI:
    """Return a cached ``AsyncOpenAI`` client, creating one if needed.

    Prior versions of this helper always instantiated a new client which left
    open HTTP connections behind.  We now reuse a module-level singleton to
    avoid leaking resources.  Tests that need isolation can still call
    ``close_client`` to reset the cache.
    """

    global _client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    if _client is None:
        _client = AsyncOpenAI(api_key=api_key)
    return _client


async def close_client() -> None:
    """Close the cached client and reset the singleton."""

    global _client
    if _client is not None:
        await _client.close()
        _client = None


# Sentinel for pytest runs
_TEST_MODE = bool(os.getenv("PYTEST_CURRENT_TEST"))


async def ask_gpt(
    prompt: str,
    model: str | None = None,
    system: str | None = None,
    *,
    stream: bool = False,
    on_token: Callable[[str], Awaitable[None]] | None = None,
    raw: bool = False,
    timeout: float | None = None,
    routing_decision=None,  # New parameter for routing decision
    **kwargs,  # <- allow passing allow_test and gen params
) -> tuple[str, int, int, float] | tuple[str, int, int, float, object]:
    """Return text, prompt tokens, completion tokens and total price.

    In test mode, if `allow_test=True` kwarg, returns dummy data.
    Otherwise, simulates GPT backend failure by raising RuntimeError.
    """

    if _TEST_MODE:
        if kwargs.pop("allow_test", False):
            return "gpt-dummy", 0, 0, 0.0
        raise RuntimeError("GPT backend unavailable (test stub)")

    model = _normalize_model_name(model)
    client = get_client()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    start = time.perf_counter()
    try:
        # Extract generation parameters from kwargs and map for provider
        gen_params = for_openai(kwargs)
        # Remove keys not accepted directly by OpenAI client to avoid TypeErrors
        # We'll pass only recognized args to the API call; others are ignored
        openai_kwargs = {k: v for k, v in gen_params.items() if v is not None}
        with start_span("openai.chat", {"llm.provider": "openai", "llm.model": model}):
            if stream:
                create_call = client.chat.completions.create(
                    model=model, messages=messages, stream=True, **openai_kwargs
                )
                if timeout:
                    resp_stream = await asyncio.wait_for(create_call, timeout=timeout)
                else:
                    resp_stream = await create_call
                chunks: list[str] = []
                final = None
                async for part in resp_stream:
                    delta = getattr(part.choices[0], "delta", None)
                    token = getattr(delta, "content", None)
                    if token:
                        chunks.append(token)
                        if on_token:
                            await on_token(token)
                    if getattr(part.choices[0], "finish_reason", None):
                        final = part
                resp = final
                text = "".join(chunks).strip()
            else:
                create_call = client.chat.completions.create(
                    model=model, messages=messages, **openai_kwargs
                )
                if timeout:
                    resp = await asyncio.wait_for(create_call, timeout=timeout)
                else:
                    resp = await create_call
                text = resp.choices[0].message.content.strip()
                if on_token:
                    await on_token(text)
        usage = getattr(resp, "usage", None) or {}
        pt = int(getattr(usage, "prompt_tokens", 0))
        ct = int(getattr(usage, "completion_tokens", 0))
        pricing = MODEL_PRICING.get(model, {"in": 0.0, "out": 0.0})
        if isinstance(pricing, dict):
            in_rate = float(pricing.get("in", 0.0))
            out_rate = float(pricing.get("out", 0.0))
        else:  # pragma: no cover - backward compatibility
            in_rate = out_rate = float(pricing)
        in_cost = in_rate * pt / 1000
        out_cost = out_rate * ct / 1000
        cost = in_cost + out_cost

        # telemetry & metrics
        rec = log_record_var.get()
        if rec:
            rec.model_name = model
            rec.prompt_tokens = pt
            rec.completion_tokens = ct
            rec.prompt_cost_usd = in_cost
            rec.completion_cost_usd = out_cost
            rec.cost_usd = cost

        duration = time.perf_counter() - start
        REQUEST_COUNT.labels("ask_gpt", "chat", model).inc()
        REQUEST_LATENCY.labels("ask_gpt", "chat", model).observe(duration)
        MODEL_LATENCY_SECONDS.labels(model).observe(duration)
        REQUEST_COST.labels("ask_gpt", "chat", model, "prompt").observe(in_cost)
        REQUEST_COST.labels("ask_gpt", "chat", model, "completion").observe(out_cost)
        REQUEST_COST.labels("ask_gpt", "chat", model, "total").observe(cost)

        if raw:
            return text, pt, ct, cost, resp
        return text, pt, ct, cost
    except Exception as e:
        logger.exception("OpenAI request failed: %s", e)
        raise


async def stream_gpt(
    prompt: str,
    model: str | None = None,
    system: str | None = None,
    **kwargs,
) -> AsyncIterator[str]:
    """Yield GPT tokens as they are produced.

    This helper wraps :func:`ask_gpt` and exposes the token stream as an async
    iterator which is convenient for voice adapters like ``PipecatSession``.
    Additional keyword arguments are forwarded to :func:`ask_gpt`.
    """

    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _on_token(token: str) -> None:
        await queue.put(token)

    async def _runner() -> None:
        await ask_gpt(
            prompt,
            model=model,
            system=system,
            stream=True,
            on_token=_on_token,
            **kwargs,
        )
        await queue.put(None)

    asyncio.create_task(_runner())

    while True:
        tok = await queue.get()
        if tok is None:
            break
        yield tok


__all__ = ["ask_gpt", "stream_gpt", "SYSTEM_PROMPT"]
