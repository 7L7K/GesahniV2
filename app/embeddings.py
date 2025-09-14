from __future__ import annotations

"""Embedding utilities supporting OpenAI and local LLaMA backends.

This module exposes a single :func:`embed` coroutine which returns a vector of
floats for a given input text. The backend is selected via the
``EMBEDDING_BACKEND`` environment variable and can be ``"openai"``,
``"llama"``, or ``"stub"``.

When using the LLaMA backend a local ``gguf`` model path must be supplied via
``LLAMA_EMBEDDINGS_MODEL``. The embeddings for LLaMA are produced using
``llama-cpp-python`` which executes synchronously and is therefore dispatched to
``asyncio``'s default executor.

Simple benchmarking helpers are included to measure latency and throughput of
repeated embedding calls.
"""


import asyncio
import hashlib
import logging
import os
import time
from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

from .metrics import EMBEDDING_LATENCY_SECONDS

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from openai import OpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globals & config
# ---------------------------------------------------------------------------

_TTL = 24 * 60 * 60  # seconds, for OpenAI sync cache bucket
_llama_model = None

# Optional dependency
try:  # pragma: no cover
    from llama_cpp import Llama  # type: ignore
except Exception:  # pragma: no cover
    Llama = None  # type: ignore


# ---------------------------------------------------------------------------
# Deterministic stub (for tests / in-memory stores)
# ---------------------------------------------------------------------------


def _embed_stub(text: str) -> list[float]:
    """Return a deterministic local embedding used for tests and in-memory stores.

    8-dim “thumbprint” keeps semantic-cache tests meaningful without external calls.
    """
    h = hashlib.sha256(text.encode()).digest()
    return (
        np.frombuffer(h[:32], dtype=np.uint8)
        .astype("float32")
        .reshape(8, 4)
        .mean(axis=1)
        .tolist()
    )


# ---------------------------------------------------------------------------
# LLaMA backend (sync init, run in executor)
# ---------------------------------------------------------------------------


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


def _reset_llama_model_for_tests():  # pragma: no cover - test helper
    global _llama_model
    _llama_model = None


# ---------------------------------------------------------------------------
# OpenAI backend (sync path with TTL cache)
# ---------------------------------------------------------------------------


def get_openai_client() -> OpenAI:
    """Return a synchronous OpenAI client (instantiate per call for test isolation)."""
    from openai import OpenAI  # type: ignore

    return OpenAI()


def get_qdrant_client():
    """Return a lazy Qdrant client (instantiate on first call for startup performance)."""
    from app.memory.vector_store.qdrant import QdrantVectorStore  # type: ignore

    # Return the QdrantVectorStore instance (lazy instantiation)
    return QdrantVectorStore()


@lru_cache(maxsize=5_000)
def _embed_openai_sync(text: str, ttl_bucket: int) -> list[float]:
    """Return an embedding using the OpenAI sync client (cached by TTL bucket)."""
    client = get_openai_client()
    model = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    try:
        resp = client.embeddings.create(
            model=model, input=text, encoding_format="float"
        )
    except TypeError:
        # Older SDKs / stubs that don't accept encoding_format
        resp = client.embeddings.create(model=model, input=text)

    embedding = resp.data[0].embedding
    if isinstance(embedding, str):  # pragma: no cover - safety hatch for base64
        try:
            try:
                import pybase64 as base64  # type: ignore
            except Exception:
                import base64  # type: ignore
            raw = base64.b64decode(embedding)
            return np.frombuffer(raw, dtype=np.float32).astype("float32").tolist()
        except Exception as e:
            raise RuntimeError(
                "Unexpected base64 embedding format from OpenAI API"
            ) from e
    return embedding  # type: ignore[return-value]


async def _embed_openai(text: str) -> list[float]:
    """Asynchronously compute an OpenAI embedding with caching."""
    bucket = int(time.time() // _TTL)
    loop = asyncio.get_running_loop()
    t0 = time.perf_counter()
    try:
        vec = await loop.run_in_executor(None, _embed_openai_sync, text, bucket)
        # Flatten any nested structure and ensure length matches EMBED_DIM if set
        try:
            from app.config_runtime import CONFIG

            exp_dim = CONFIG.embed_dim
        except Exception:
            exp_dim = int(os.getenv("EMBED_DIM", "1536"))

        # Flatten nested lists (some SDKs return nested arrays)
        def _flatten(v):
            out = []
            for item in v:
                if isinstance(item, list | tuple):
                    out.extend(_flatten(item))
                else:
                    out.append(item)
            return out

        flat = _flatten(vec)
        if exp_dim and len(flat) != exp_dim and exp_dim != 0:
            logger.warning(
                "embed_dim_mismatch: EMBED_DIM=%s but embedding length=%s",
                exp_dim,
                len(flat),
            )
        return flat
    finally:
        try:
            EMBEDDING_LATENCY_SECONDS.labels("openai").observe(time.perf_counter() - t0)
        except Exception:
            pass


async def _embed_llama(text: str) -> list[float]:
    model = _get_llama_model()

    def _run() -> list[float]:
        result = model.create_embedding(text)
        return result["data"][0]["embedding"]

    loop = asyncio.get_running_loop()
    t0 = time.perf_counter()
    try:
        return await loop.run_in_executor(None, _run)
    finally:
        try:
            EMBEDDING_LATENCY_SECONDS.labels("llama").observe(time.perf_counter() - t0)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def embed_sync(text: str) -> list[float]:
    """Synchronous helper used by vector stores."""
    backend = os.getenv("EMBEDDING_BACKEND", "openai").lower()

    # In CI/pytest or when using in-memory vector store, force stub to avoid network.
    if backend != "stub" and (
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("VECTOR_STORE", "").lower() in {"memory", "inmemory"}
    ):
        backend = "stub"

    model = (
        os.getenv("EMBED_MODEL", "text-embedding-3-small")
        if backend == "openai"
        else os.getenv("LLAMA_EMBEDDINGS_MODEL", "")
    )
    logger.debug(
        "embed_sync backend=%s model=%s (cosine metric assumed)", backend, model
    )

    t0 = time.perf_counter()
    try:
        if backend == "stub":
            return _embed_stub(text)
        if backend == "openai":
            bucket = int(time.time() // _TTL)
            return _embed_openai_sync(text, bucket)
        if backend == "llama":
            result = _get_llama_model().create_embedding(text)
            return result["data"][0]["embedding"]
    finally:
        try:
            EMBEDDING_LATENCY_SECONDS.labels(backend).observe(time.perf_counter() - t0)
        except Exception:
            pass
    raise ValueError(f"Unsupported EMBEDDING_BACKEND: {backend}")


async def embed(text: str) -> list[float]:
    """Return an embedding vector for ``text`` (async).

    Backend chosen by ``EMBEDDING_BACKEND`` (default: ``openai``).
    """
    backend = os.getenv("EMBEDDING_BACKEND", "openai").lower()

    # Mirror sync behavior for tests / memory store
    if backend != "stub" and (
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("VECTOR_STORE", "").lower() in {"memory", "inmemory"}
    ):
        backend = "stub"

    model = (
        os.getenv("EMBED_MODEL", "text-embedding-3-small")
        if backend == "openai"
        else os.getenv("LLAMA_EMBEDDINGS_MODEL", "")
    )
    logger.debug("embed backend=%s model=%s (cosine metric assumed)", backend, model)

    if backend == "openai":
        return await _embed_openai(text)
    if backend == "llama":
        return await _embed_llama(text)
    if backend == "stub":
        return _embed_stub(text)
    raise ValueError(f"Unsupported EMBEDDING_BACKEND: {backend}")


async def benchmark(
    text: str, iterations: int = 10, user_id: str | None = None
) -> dict[str, float]:
    """Run ``embed`` ``iterations`` times and log latency & throughput.

    ``user_id`` is accepted for interface parity but is not used.
    """
    start = time.perf_counter()
    for _ in range(iterations):
        await embed(text)
    elapsed = time.perf_counter() - start
    latency = elapsed / iterations if iterations else 0.0
    throughput = iterations / elapsed if elapsed else 0.0
    logger.info(
        "embeddings.benchmark",
        extra={
            "meta": {"latency": round(latency, 6), "throughput": round(throughput, 6)}
        },
    )
    return {"latency": latency, "throughput": throughput}


__all__ = ["embed", "benchmark", "embed_sync"]
