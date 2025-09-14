import asyncio
import os
from typing import Any

_client = None


def _init_client():
    """Lazy initialize OpenAI client placeholder.

    Keep import/initialization out of top-level so module import is cheap.
    Replace this with real client creation and caching as needed.
    """
    global _client
    if _client is not None:
        return _client

    # Minimal validation of configuration
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OpenAI API key not configured")

    # TODO: replace with real async client creation and caching
    _client = object()
    return _client


async def openai_router(payload: dict[str, Any]) -> dict[str, Any]:
    """Call OpenAI backend with standardized response format.

    Frozen response contract:
    {
      "backend": "openai",
      "model": "string",
      "answer": "string",
      "usage": {"input_tokens": 0, "output_tokens": 0}
    }

    Raises RuntimeError if backend unavailable (will be caught as 503).
    """
    # Ensure client exists (synchronous init allowed here)
    try:
        _init_client()
    except Exception as e:
        raise RuntimeError("OpenAI backend unavailable: %s" % e)

    # TODO: perform real async call using the cached client
    # For now, return standardized dry-run response
    await asyncio.sleep(0)  # keep function truly async

    model = payload.get("model", "gpt-4o")
    return {
        "backend": "openai",
        "model": model,
        "answer": "(dry-run OpenAI response)",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
