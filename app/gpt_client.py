# app/gpt_client.py

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

import logging
import os

try:  # pragma: no cover - exercised when openai is installed
    from openai import AsyncOpenAI

    OPENAI_AVAILABLE = True
except Exception:  # pragma: no cover - executed when dependency missing
    OPENAI_AVAILABLE = False

    class AsyncOpenAI:  # type: ignore[misc]
        """Fallback used when the ``openai`` package isn't available."""

        def __init__(self, *_, **__):  # pragma: no cover - simple stub
            raise RuntimeError("openai package not installed")


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Temporary system prompt to prime the assistant
SYSTEM_PROMPT = "You are a helpful assistant."

logger = logging.getLogger(__name__)
_client: AsyncOpenAI | None = None

# price in USD per 1k tokens
MODEL_PRICING = {
    "gpt-4o": 0.005,
    "gpt-3.5-turbo": 0.002,
    "gpt-4": 0.01,
}


def get_client() -> AsyncOpenAI:
    """Return a singleton ``AsyncOpenAI`` client.

    The API key is fetched at call time so tests can monkeypatch the
    environment. If the key is missing a ``RuntimeError`` is raised.
    """

    global _client
    if not OPENAI_AVAILABLE:
        raise RuntimeError("openai package not installed")
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


async def close_client() -> None:
    """Close the cached client and reset the singleton."""

    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def ask_gpt(
    prompt: str, model: str | None = None, system: str | None = None
) -> tuple[str, int, int, float]:
    """Return text, prompt tokens, completion tokens and price per 1k tokens."""
    model = model or OPENAI_MODEL
    client = get_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
        )
        text = resp.choices[0].message.content.strip()
        usage = resp.usage or {}
        pt = int(getattr(usage, "prompt_tokens", 0))
        ct = int(getattr(usage, "completion_tokens", 0))
        unit_price = MODEL_PRICING.get(model, 0.0)
        return text, pt, ct, unit_price
    except Exception as e:
        logger.exception("OpenAI request failed: %s", e)
        raise


__all__ = ["get_client", "close_client", "ask_gpt", "MODEL_PRICING", "SYSTEM_PROMPT"]
