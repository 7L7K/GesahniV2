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
import hashlib
import numpy as np   # <- new



if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from openai import OpenAI

logger = logging.getLogger(__name__)


_llama_model = None

def embed_sync(text: str) -> List[float]:
    """Synchronous helper used by vector stores.

    • In CI / pytest we short-circuit to a deterministic local vector so no
      network calls ever happen.
    """
    if os.getenv("PYTEST_CURRENT_TEST") or \
       os.getenv("VECTOR_STORE", "").lower() in {"memory", "inmemory"}:
        # 8-dim “thumbprint” to keep semantic-cache tests meaningful
        h = hashlib.sha256(text.encode()).digest()
        return np.frombuffer(h[:32], dtype=np.uint8).astype("float32")\
                 .reshape(8, 4).mean(axis=1).tolist()

    bucket = int(time.time() // _TTL)
    return _embed_openai_sync(text, bucket)


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
    # Explicitly request float encoding to avoid base64 payloads returned by newer SDKs
    resp = client.embeddings.create(
        model=model,
        input=text,
        encoding_format="float",
    )
    embedding = resp.data[0].embedding
    # Defensive: if a base64 string is ever returned, decode to float32
    if isinstance(embedding, str):  # pragma: no cover - safety hatch
        try:
            try:
                import pybase64 as base64  # type: ignore
            except Exception:  # fallback to stdlib
                import base64  # type: ignore
            raw = base64.b64decode(embedding)
            vec = np.frombuffer(raw, dtype=np.float32).astype("float32").tolist()
            return vec
        except Exception:
            # Re-raise with context so callers see a clear error
            raise RuntimeError("Unexpected base64 embedding format from OpenAI API")
    return embedding  # type: ignore[return-value]


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
