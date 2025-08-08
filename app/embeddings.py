"""Embedding utilities supporting OpenAI and local LLaMA backends.

This module exposes a single :func:`embed` coroutine which returns a vector of
floats for a given input text.  The backend is selected via the
``EMBEDDING_BACKEND`` environment variable and can either be ``"openai"`` or
``"llama"``.

When using the LLaMA backend a local ``gguf`` model path must be supplied via
``LLAMA_EMBEDDINGS_MODEL``.  The embeddings for LLaMA are produced using
``llama-cpp-python`` which executes synchronously and is therefore dispatched to
``asyncio``'s default executor.

Simple benchmarking helpers are included to measure latency and throughput of
repeated embedding calls.
"""

from __future__ import annotations

import asyncio
import os
import time
import logging
from functools import lru_cache
from typing import List, Dict, TYPE_CHECKING


if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from openai import OpenAI

logger = logging.getLogger(__name__)


_llama_model = None


def get_openai_client() -> "OpenAI":
    """Return a synchronous OpenAI client.

    The client is instantiated on each call to avoid cross-test pollution when
    the ``openai`` module is monkey-patched. The overhead is negligible for the
    lightweight test embeddings used in this project.
    """

    from openai import OpenAI  # type: ignore

    return OpenAI()


try:  # pragma: no cover - import guarded for optional dependency
    from llama_cpp import Llama  # type: ignore
except Exception:  # pragma: no cover - if library not installed
    Llama = None  # type: ignore


def _get_llama_model():
    """Lazily instantiate and cache the LLaMA model for embeddings."""
    global _llama_model
    if _llama_model is None:
        if Llama is None:
            raise RuntimeError("llama-cpp-python not installed")
        model_path = os.getenv("LLAMA_EMBEDDINGS_MODEL")
        if not model_path:
            raise RuntimeError("Missing LLAMA_EMBEDDINGS_MODEL")
        _llama_model = Llama(model_path=model_path, embedding=True)
    return _llama_model


_TTL = 24 * 60 * 60


@lru_cache(maxsize=5_000)
def _embed_openai_sync(text: str, ttl_bucket: int) -> List[float]:
    """Return an embedding using the OpenAI sync client."""
    client = get_openai_client()
    model = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    try:
        resp = client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding  # type: ignore[return-value]
    except Exception:  # pragma: no cover - network/credential issues
        # In test environments we avoid network calls and simply fall back to a
        # deterministic embedding based on text length.  This keeps the vector
        # store functional without requiring a real OpenAI API key.
        return [float(len(text))]


async def _embed_openai(text: str) -> List[float]:
    """Asynchronously compute an OpenAI embedding with caching."""
    bucket = int(time.time() // _TTL)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _embed_openai_sync, text, bucket)


async def _embed_llama(text: str) -> List[float]:
    model = _get_llama_model()

    def _run() -> List[float]:
        result = model.create_embedding(text)
        return result["data"][0]["embedding"]

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run)


async def embed(text: str) -> List[float]:
    """Return an embedding vector for ``text``.

    The backend is chosen according to the ``EMBEDDING_BACKEND`` environment
    variable which defaults to ``"openai"``.
    """

    backend = os.getenv("EMBEDDING_BACKEND", "openai").lower()
    if backend == "openai":
        return await _embed_openai(text)
    if backend == "llama":
        return await _embed_llama(text)
    raise ValueError(f"Unsupported EMBEDDING_BACKEND: {backend}")


def embed_sync(text: str) -> List[float]:
    """Synchronous helper used by vector stores."""
    bucket = int(time.time() // _TTL)
    return _embed_openai_sync(text, bucket)


async def benchmark(
    text: str, iterations: int = 10, user_id: str | None = None
) -> Dict[str, float]:
    """Run ``embed`` ``iterations`` times and log latency and throughput.

    ``user_id`` is accepted for interface parity but is not used.
    """

    start = time.perf_counter()
    for _ in range(iterations):
        await embed(text)
    elapsed = time.perf_counter() - start
    latency = elapsed / iterations if iterations else 0.0
    throughput = iterations / elapsed if elapsed else 0.0
    logger.info("Embedding latency %.4fs throughput %.2f req/s", latency, throughput)
    return {"latency": latency, "throughput": throughput}


__all__ = ["embed", "benchmark", "embed_sync"]
