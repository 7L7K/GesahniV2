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
from typing import List, Dict, TYPE_CHECKING


if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_openai_client: "AsyncOpenAI | None" = None
_llama_model = None


def get_openai_client() -> "AsyncOpenAI":
    """Return a cached AsyncOpenAI client."""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI  # type: ignore

        _openai_client = AsyncOpenAI()
    return _openai_client


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


async def _embed_openai(text: str) -> List[float]:
    client = get_openai_client()
    resp = await client.embeddings.create(
        model="text-embedding-3-small", input=text
    )
    return resp.data[0].embedding  # type: ignore[return-value]


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


async def benchmark(text: str, iterations: int = 10) -> Dict[str, float]:
    """Run ``embed`` ``iterations`` times and log latency and throughput."""

    start = time.perf_counter()
    for _ in range(iterations):
        await embed(text)
    elapsed = time.perf_counter() - start
    latency = elapsed / iterations if iterations else 0.0
    throughput = iterations / elapsed if elapsed else 0.0
    logger.info(
        "Embedding latency %.4fs throughput %.2f req/s", latency, throughput
    )
    return {"latency": latency, "throughput": throughput}

