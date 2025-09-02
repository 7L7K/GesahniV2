from __future__ import annotations
"""High level vector store API used throughout the project."""


import logging
import os
import time

from app import metrics
from app.redaction import redact_pii, store_redaction_map
from app.telemetry import hash_user_id

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
            raise RuntimeError(
                f"ChromaVectorStore unavailable: {_CHROMA_IMPORT_ERROR!r}"
            )


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
    if (os.getenv("STRICT_VECTOR_STORE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    # Treat staging/production-like envs as strict by default
    env = (os.getenv("ENV") or os.getenv("APP_ENV") or "").strip().lower()
    if env in {"production", "prod", "staging", "preprod", "preview"}:
        return True
    return False


def _get_store() -> VectorStore:
    """Return the configured vector store backend using unified VECTOR_DSN configuration.

    Uses the new unified_store.create_vector_store() factory which supports:
    - memory:// (in-memory store for tests)
    - chroma:///path/to/data (local ChromaDB)
    - chroma+cloud://tenant.database?api_key=xxx (Chroma Cloud)
    - qdrant://host:port?api_key=xxx (Qdrant HTTP)
    - qdrant+grpc://host:port?api_key=xxx (Qdrant gRPC)
    - dual://qdrant://host:port?api_key=xxx&chroma_path=/path (Dual read)

    Maintains backward compatibility with legacy VECTOR_STORE env var.
    """
    try:
        from .unified_store import create_vector_store

        store = create_vector_store()

        # Record metrics
        logger.debug("Vector store backend selected: %s", type(store).__name__)
        try:
            name = type(store).__name__
            if name == "QdrantVectorStore":
                metrics.VECTOR_SELECTED_TOTAL.labels("qdrant").inc()
            elif name == "DualReadVectorStore":
                metrics.VECTOR_SELECTED_TOTAL.labels("dual").inc()
            elif name == "ChromaVectorStore":
                # Check if it's cloud mode
                dsn = os.getenv("VECTOR_DSN", "")
                if "cloud" in dsn or os.getenv("VECTOR_STORE") == "cloud":
                    metrics.VECTOR_SELECTED_TOTAL.labels("cloud").inc()
                else:
                    metrics.VECTOR_SELECTED_TOTAL.labels("chroma").inc()
            else:
                metrics.VECTOR_SELECTED_TOTAL.labels("memory").inc()
        except Exception:
            pass

        if type(store).__name__ == "QdrantVectorStore":
            logger.info(
                "VectorStore: Qdrant initialized with cosine metric; threshold sim>=0.75 (dist<=0.25)"
            )

        return store

    except Exception as exc:
        if _strict_mode():
            logger.error("FATAL: Vector store init failed: %s", exc)
            raise

        logger.warning(
            "Vector store init failed (%s: %s); falling back to MemoryVectorStore",
            type(exc).__name__,
            exc,
        )
        try:
            metrics.VECTOR_INIT_FALLBACKS.labels(
                requested="unified", reason=type(exc).__name__
            ).inc()
        except Exception:
            pass
        return MemoryVectorStore()


# Lazy initialization of the singleton store instance
_store: VectorStore | None = None


def get_store() -> VectorStore:
    """Factory for obtaining the vector store.

    Uses lazy initialization to avoid import-time failures.
    In production, do not silently fall back; reuse singleton to avoid churn.
    In tests/dev, return the module-level instance.
    """
    global _store
    if _store is None:
        _store = _get_store()
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
    mem_id = get_store().add_user_memory(user_id, redacted)
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
) -> list[str]:
    """Retrieve up to *k* memories relevant to *prompt* for the given user."""
    k_int = _coerce_k(k)
    logger.debug(
        "query_user_memories args: user=%s prompt=%r k=%d",
        hash_user_id(user_id),
        prompt,
        k_int,
    )
    res = get_store().query_user_memories(user_id, prompt, k_int)
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
    get_store().cache_answer(cid, doc, answer)


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


def lookup_cached_answer(prompt: str, ttl_seconds: int = 86400) -> str | None:
    """Return a cached answer.

    If *prompt* looks like a deterministic cache id (e.g. "v1|…|…|"), perform
    an exact id lookup via the backing ``qa_cache`` to avoid semantic bleeding
    across models. Otherwise, fallback to the vector similarity lookup.
    """
    # Fast path: exact id style (vN|...|...|)
    is_cid = (
        isinstance(prompt, str) and "|" in prompt and prompt[:2].lower().startswith("v")
    )
    if is_cid:
        try:
            res = get_store().qa_cache.get_items(ids=[prompt], include=["metadatas"])  # type: ignore[attr-defined]
            metas = (res.get("metadatas") or [None])[0] or {}
            ts = float(metas.get("timestamp", 0) or 0)
            if ttl_seconds and ts and (time.time() - ts > ttl_seconds):  # type: ignore[name-defined]
                # best-effort invalidate via collection
                try:
                    get_store().qa_cache.delete(ids=[prompt])  # type: ignore[attr-defined]
                except Exception:
                    pass
                return None
            if metas.get("feedback") == "down":
                try:
                    get_store().qa_cache.delete(ids=[prompt])  # type: ignore[attr-defined]
                except Exception:
                    pass
                return None
            ans = metas.get("answer")
            return ans if isinstance(ans, str) else None
        except Exception:
            # Fall back to similarity path on any collection mismatch
            pass

    return get_store().lookup_cached_answer(prompt, ttl_seconds)


def _compose_cache_cid(
    user_id: str | None, norm_prompt: str, system_prompt: str | None, model_family: str | None
) -> str:
    """Compose a namespaced cache id to avoid cross-user and cross-system reuse.

    Format: v1|<user_hash>|<prompt_hash>|<system_hash>|<model_family>
    """
    # Hash user id for privacy while preventing cross-user reuse
    try:
        user_hash = hash_user_id(user_id) if user_id else "anon"
    except Exception:
        user_hash = "anon"
    p_hash = _normalized_hash(norm_prompt)
    s_hash = _normalized_hash(system_prompt or "")
    mf = (model_family or "")
    cid = f"v1|{user_hash}|{p_hash}|{s_hash}|{mf}"
    return cid


def lookup_cached_answer_context(
    user_id: str | None,
    norm_prompt: str,
    system_prompt: str | None,
    model_family: str | None,
    ttl_seconds: int = 86400,
) -> str | None:
    """Lookup a cached answer scoped to user, normalized prompt, system prompt, and model family."""
    cid = _compose_cache_cid(user_id, norm_prompt, system_prompt, model_family)
    return lookup_cached_answer(cid, ttl_seconds)


def cache_answer_context(
    user_id: str | None,
    norm_prompt: str,
    system_prompt: str | None,
    model_family: str | None,
    answer: str,
    ttl_seconds: int | None = None,
) -> None:
    """Store an answer under the composed, namespaced cache id."""
    cid = _compose_cache_cid(user_id, norm_prompt, system_prompt, model_family)
    cache_answer(prompt=norm_prompt, answer=answer, cache_id=cid)


def record_feedback(prompt: str, feedback: str) -> None:
    """Record human feedback for *prompt*."""
    return get_store().record_feedback(prompt, feedback)


class _QACacheProxy:
    """Thin proxy so callers can treat ``qa_cache`` like a module-level var."""

    def __call__(self):  # noqa: D401
        return get_store().qa_cache

    def __getattr__(self, name):  # pragma: no cover - simple delegation
        return getattr(get_store().qa_cache, name)


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
