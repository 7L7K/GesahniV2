"""High level vector store API used throughout the project."""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import List, Optional

from app.telemetry import hash_user_id
from app import metrics
from app.redaction import redact_pii, store_redaction_map

# ---------------------------------------------------------------------------
# Export real ChromaVectorStore if available, but ALWAYS define the symbol
# so "from app.memory.api import ChromaVectorStore" never fails during
# pytest collection or when Chroma deps are missing.
# ---------------------------------------------------------------------------
try:
    from .chroma_store import ChromaVectorStore  # real implementation
    _CHROMA_IMPORT_ERROR: Exception | None = None
except Exception as _e:  # pragma: no cover - exercised only when chroma not importable
    _CHROMA_IMPORT_ERROR = _e

    class ChromaVectorStore:  # type: ignore
        """Sentinel implementation that preserves the symbol for imports.

        Instantiation will raise with the original import error, but test
        collection and `from ... import ChromaVectorStore` won’t explode.
        """
        AVAILABLE = False

        def __init__(self, *a, **kw) -> None:
            raise RuntimeError(f"ChromaVectorStore unavailable: {_CHROMA_IMPORT_ERROR!r}")

from .env_utils import _get_mem_top_k, _normalized_hash
from .memory_store import MemoryVectorStore, VectorStore
try:
    from .vector_store.qdrant import QdrantVectorStore  # type: ignore
except Exception:  # pragma: no cover - optional
    QdrantVectorStore = None  # type: ignore
try:
    from .vector_store.dual import DualReadVectorStore  # type: ignore
except Exception:  # pragma: no cover - optional
    DualReadVectorStore = None  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend selection helpers
# ---------------------------------------------------------------------------

def _strict_mode() -> bool:
    """Return True if strict init policy is enabled.

    In strict mode, any backend initialisation error is fatal, regardless of
    the environment. Enable with ``STRICT_VECTOR_STORE=1|true|yes``.
    """
    if (os.getenv("STRICT_VECTOR_STORE") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    # Treat staging/production-like envs as strict by default
    env = (os.getenv("ENV") or os.getenv("APP_ENV") or "").strip().lower()
    if env in {"production", "prod", "staging", "preprod", "preview"}:
        return True
    return False


def _get_store() -> VectorStore:
    """Return the configured vector store backend.

    * ``VECTOR_STORE`` env-var controls the preferred backend.
    * Defaults: when unset, prefer Chroma if CHROMA_PATH is set; otherwise memory in tests.
    * Falls back to in-memory only when an explicit backend fails and strict mode is disabled.
    """
    raw_kind = (os.getenv("VECTOR_STORE") or "").strip().lower()
    allowed = {"memory", "inmemory", "chroma", "cloud", "qdrant", "dual", ""}
    kind = raw_kind if raw_kind in allowed else "_unknown_"
    chroma_path = os.getenv("CHROMA_PATH", ".chroma_data")

    try:
        if kind in ("memory", "inmemory"):
            logger.info("Using MemoryVectorStore (VECTOR_STORE=%s)", kind)
            store: VectorStore = MemoryVectorStore()
        else:
            if kind == "":
                is_pytest = ("PYTEST_CURRENT_TEST" in os.environ) or ("pytest" in sys.modules)
                requested_kind = "chroma" if chroma_path else ("memory" if is_pytest else "chroma")
            elif kind == "_unknown_":
                if _strict_mode():
                    raise RuntimeError(f"Unknown VECTOR_STORE={raw_kind!r} under STRICT_VECTOR_STORE")
                logger.warning("Unknown VECTOR_STORE=%r; defaulting to ChromaVectorStore", raw_kind)
                try:
                    metrics.VECTOR_INIT_FALLBACKS.labels(requested=raw_kind or "(empty)", reason="unknown_kind").inc()
                except Exception:
                    pass
                requested_kind = "chroma"
            else:
                requested_kind = kind

            if requested_kind == "memory":
                # Disallow in non-test environments to avoid per-process drift
                env = (os.getenv("ENV") or os.getenv("APP_ENV") or "").strip().lower()
                is_test = ("PYTEST_CURRENT_TEST" in os.environ) or ("pytest" in sys.modules) or env == "test"
                if not is_test:
                    raise RuntimeError("MemoryVectorStore is restricted to tests/dev environments")
                store = MemoryVectorStore()
            elif requested_kind == "dual":
                if DualReadVectorStore is None:
                    raise RuntimeError("DualReadVectorStore unavailable (qdrant/chroma deps missing)")
                logger.info("Initializing DualReadVectorStore (Qdrant primary, Chroma fallback)")
                store = DualReadVectorStore()  # type: ignore[call-arg]
            elif requested_kind == "qdrant":
                if QdrantVectorStore is None:
                    raise RuntimeError("QdrantVectorStore unavailable (qdrant-client not installed)")
                logger.info("Initializing QdrantVectorStore")
                store = QdrantVectorStore()  # type: ignore[call-arg]
            else:
                if not chroma_path:
                    raise FileNotFoundError("CHROMA_PATH is empty")
                logger.info("Initializing ChromaVectorStore at path: %s", chroma_path)
                store = ChromaVectorStore()
    except Exception as exc:
        # In strict mode, never fallback — including when VECTOR_STORE is unknown
        if _strict_mode():
            logger.error("FATAL: Vector store init failed: %s", exc)
            raise
        requested = (requested_kind if "requested_kind" in locals() else (kind or "chroma"))
        backend_label = (
            "DualReadVectorStore" if requested == "dual" else
            "QdrantVectorStore" if requested == "qdrant" else
            "MemoryVectorStore" if requested == "memory" else
            "ChromaVectorStore"
        )
        logger.warning("%s unavailable (%s: %s); falling back to MemoryVectorStore", backend_label, type(exc).__name__, exc)
        try:
            metrics.VECTOR_INIT_FALLBACKS.labels(requested=requested, reason=type(exc).__name__).inc()
        except Exception:
            pass
        store = MemoryVectorStore()

    logger.debug("Vector store backend selected: %s", type(store).__name__)
    try:
        name = type(store).__name__
        if name == "QdrantVectorStore":
            metrics.VECTOR_SELECTED_TOTAL.labels("qdrant").inc()
        elif name == "DualReadVectorStore":
            metrics.VECTOR_SELECTED_TOTAL.labels("dual").inc()
        elif name == "ChromaVectorStore":
            metrics.VECTOR_SELECTED_TOTAL.labels(
                "cloud" if (os.getenv("VECTOR_STORE", "").strip().lower() == "cloud") else "chroma"
            ).inc()
        else:
            metrics.VECTOR_SELECTED_TOTAL.labels("memory").inc()
    except Exception:
        pass
    if type(store).__name__ == "QdrantVectorStore":
        logger.info("VectorStore: Qdrant initialized with cosine metric; threshold sim>=0.75 (dist<=0.25)")
    return store


# The singleton store instance used by every helper below.
_store: VectorStore = _get_store()


def get_store() -> VectorStore:
    """Factory for obtaining the vector store.

    In production, do not silently fall back; reuse singleton to avoid churn.
    In tests/dev, return the module-level instance.
    """
    if os.getenv("ENV", "").lower() == "production":
        return _store
    return _store

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def add_user_memory(user_id: str, memory: str) -> str:
    """Persist a single memory string for *user_id* with PII redaction.

    The original-to-placeholder substitution map is stored separately under
    `data/redactions/user_memory/<mem_id>.json` and is access-controlled at the
    filesystem level.
    """
    redacted, mapping = redact_pii(memory)
    mem_id = _store.add_user_memory(user_id, redacted)
    try:
        store_redaction_map("user_memory", mem_id, mapping)
    except Exception:
        pass
    return mem_id


def _coerce_k(k: int | str | None) -> int:
    """Return a positive integer ``k`` with sane fall-backs.

    Any falsy or invalid value is replaced by the project-wide default from
    :func:`env_utils._get_mem_top_k`.
    """
    raw = k
    if k is None:
        result = _get_mem_top_k()
    else:
        try:
            value = int(k)
        except (TypeError, ValueError):
            result = _get_mem_top_k()
        else:
            result = value if value > 0 else _get_mem_top_k()

    logger.debug("_coerce_k: raw=%r resolved=%d", raw, result)
    return result


def query_user_memories(
    user_id: str, prompt: str, k: int | str | None = None
) -> List[str]:
    """Retrieve up to *k* memories relevant to *prompt* for the given user."""
    k_int = _coerce_k(k)
    logger.debug(
        "query_user_memories args: user=%s prompt=%r k=%d",
        hash_user_id(user_id),
        prompt,
        k_int,
    )
    res = _store.query_user_memories(user_id, prompt, k_int)
    logger.debug("query_user_memories returned %d items", len(res))
    return res


def cache_answer(prompt: str, answer: str, cache_id: str | None = None) -> None:
    """Cache *answer* keyed by *prompt* (or explicit *cache_id*).

    When ``prompt`` looks like a composed deterministic cache id (``vN|...|``),
    we store under that exact id and mark the stored document with a special
    ``__cid__`` prefix to avoid accidental semantic matches in similarity-based
    lookups.
    """
    # Detect deterministic cache id style: v<digits>|...
    is_cid = (
        cache_id is None
        and isinstance(prompt, str)
        and "|" in prompt
        and prompt.lower().startswith("v")
    )
    if cache_id:
        cid = cache_id
        doc = prompt
    elif is_cid:
        cid = prompt
        doc = f"__cid__:{prompt}"
    else:
        cid = _normalized_hash(prompt)
        doc = prompt
    _store.cache_answer(cid, doc, answer)


def cache_answer_legacy(*args) -> None:  # pragma: no cover - shim for callers
    """Backward-compatibility wrapper for the old positional signature."""
    import warnings

    warnings.warn(
        "cache_answer positional arguments are deprecated; use "
        "cache_answer(prompt, answer, cache_id=None)",
        DeprecationWarning,
        stacklevel=2,
    )

    if len(args) == 2:
        cache_answer(args[0], args[1])
    elif len(args) == 3:
        cache_answer(args[1], args[2], cache_id=args[0])
    else:
        raise TypeError("cache_answer_legacy expects 2 or 3 arguments")


def lookup_cached_answer(prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
    """Return a cached answer.

    If *prompt* looks like a deterministic cache id (e.g. "v1|…|…|"), perform
    an exact id lookup via the backing ``qa_cache`` to avoid semantic bleeding
    across models. Otherwise, fallback to the vector similarity lookup.
    """
    # Fast path: exact id style (vN|...|...|)
    is_cid = isinstance(prompt, str) and "|" in prompt and prompt[:2].lower().startswith("v")
    if is_cid:
        try:
            res = _store.qa_cache.get_items(ids=[prompt], include=["metadatas"])  # type: ignore[attr-defined]
            metas = (res.get("metadatas") or [None])[0] or {}
            ts = float(metas.get("timestamp", 0) or 0)
            if ttl_seconds and ts and (time.time() - ts > ttl_seconds):  # type: ignore[name-defined]
                # best-effort invalidate via collection
                try:
                    _store.qa_cache.delete(ids=[prompt])  # type: ignore[attr-defined]
                except Exception:
                    pass
                return None
            if metas.get("feedback") == "down":
                try:
                    _store.qa_cache.delete(ids=[prompt])  # type: ignore[attr-defined]
                except Exception:
                    pass
                return None
            ans = metas.get("answer")
            return ans if isinstance(ans, str) else None
        except Exception:
            # Fall back to similarity path on any collection mismatch
            pass

    return _store.lookup_cached_answer(prompt, ttl_seconds)


def record_feedback(prompt: str, feedback: str) -> None:
    """Record human feedback for *prompt*."""
    return _store.record_feedback(prompt, feedback)


class _QACacheProxy:
    """Thin proxy so callers can treat ``qa_cache`` like a module-level var."""
    def __call__(self):  # noqa: D401
        return _store.qa_cache

    def __getattr__(self, name):  # pragma: no cover - simple delegation
        return getattr(_store.qa_cache, name)


qa_cache = _QACacheProxy()
_qa_cache = qa_cache  # legacy alias


def invalidate_cache(prompt: str) -> None:
    """Invalidate any cached answer that exactly matches *prompt*."""
    cid = _normalized_hash(prompt)
    logger.debug("Invalidating cache for %s", cid)
    _store.qa_cache.delete(ids=[cid])


def close_store() -> None:
    """Close and re-initialise the underlying store (used in tests)."""
    global _store
    if _store is not None:
        try:
            _store.close()
        finally:
            _store = _get_store()


def reload_store() -> None:
    """Alias for ``close_store`` to make intent explicit for callers."""
    close_store()


__all__ = [
    # helpers
    "add_user_memory",
    "query_user_memories",
    "cache_answer",
    "cache_answer_legacy",
    "lookup_cached_answer",
    "record_feedback",
    "qa_cache",
    "invalidate_cache",
    "close_store",
    "reload_store",
    # types/backends
    "VectorStore",
    "MemoryVectorStore",
    "ChromaVectorStore",
]
