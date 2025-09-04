from typing import Dict, Any
import os
import asyncio


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


async def openai_router(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call OpenAI backend (lazy client init).

    - Avoid heavy imports at module import time
    - Raise an error if backend not configured
    """
    # Ensure client exists (synchronous init allowed here)
    try:
        _init_client()
    except Exception as e:
        raise RuntimeError("OpenAI backend unavailable: %s" % e)

    # TODO: perform real async call using the cached client
    await asyncio.sleep(0)  # keep function truly async
    return {"backend": "openai", "answer": "(dry-run)"}


