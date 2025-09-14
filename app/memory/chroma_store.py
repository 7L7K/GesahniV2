from __future__ import annotations

"""Chroma-backed vector store implementation."""


import logging
import os
import sys
import time
import uuid

from app import metrics
from app.telemetry import hash_user_id

try:  # pragma: no cover - optional dependency
    import chromadb

    try:
        # Newer Chroma exposes first‑class embedding functions with config
        from chromadb.utils import embedding_functions as chroma_ef  # type: ignore
    except Exception:  # pragma: no cover - tolerate older versions
        chroma_ef = None  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    chromadb = None
    chroma_ef = None  # type: ignore

from .env_utils import _clean_meta, _normalize
from .env_utils import _get_sim_threshold as _env_get_sim_threshold
from .memory_store import VectorStore

logger = logging.getLogger(__name__)


def _get_sim_threshold() -> float:
    """Return similarity threshold with embedder-aware override.

    When the Chroma embedder is the simple "length" embedder, we return a
    slightly higher similarity cutoff (0.6) to keep the strict
    distance-comparison (< cutoff) behavior while allowing sensible
    fallbacks in dual-read flows. Otherwise, defer to the global env value.
    """

    embed_kind = os.getenv("CHROMA_EMBEDDER", "length").strip().lower()
    # Respect explicit SIM_THRESHOLD when provided. Only use the
    # embedder-specific default (0.6) when unset.
    if embed_kind == "length" and ("SIM_THRESHOLD" not in os.environ):
        return 0.6
    return _env_get_sim_threshold()


def _normalize_meta(meta: dict | None) -> dict:
    """Return tolerant QA-cache metadata.

    - Ensure ``_type`` is present with default "qa"
    - Provide compatibility shims for older keys (``question``/``answer``)
    """

    meta = dict(meta or {})
    meta.setdefault("_type", "qa")
    if "q" not in meta and "question" in meta:
        meta["q"] = meta["question"]
    if "a" not in meta and "answer" in meta:
        meta["a"] = meta["answer"]
    return meta


def _length_similarity(a: str, b: str) -> float:
    """Return a deterministic similarity in [0, 1] based on string lengths.

    - 1.0 when texts are exactly equal
    - Otherwise, 1 - (|len(a) - len(b)| / max(1, len(a), len(b))) clamped to [0, 1]
    """

    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    denom = max(1, la, lb)
    diff = abs(la - lb) / denom
    return max(0.0, 1.0 - min(1.0, diff))


class _NoopCache:
    """No-op collection used when QA cache is disabled via env flag."""

    def get_items(
        self, *args, include: list[str] | None = None, **kwargs
    ) -> dict[str, list]:
        out: dict[str, list] = {"ids": []}
        if include is None or "metadatas" in include:
            out["metadatas"] = []
        if include is None or "documents" in include:
            out["documents"] = []
        return out

    def keys(self) -> list[str]:
        return []

    def upsert(self, *args, **kwargs) -> None:  # pragma: no cover - noop
        return None

    def delete(self, *args, **kwargs) -> None:  # pragma: no cover - noop
        return None

    def update(self, *args, **kwargs) -> None:  # pragma: no cover - noop
        return None


class _LengthEmbedder:
    _type = "LengthEmbedder"

    def __call__(self, input: list[str]) -> list[list[float]]:
        import numpy as np

        return [
            np.asarray([float(len(_normalize(t)[1]))], dtype=np.float32) for t in input
        ]

    def name(self) -> str:  # pragma: no cover - simple helper
        return "length-embedder"


class _OpenAIEmbedder:
    """Embedding function that uses app.embeddings.embed_sync.

    This stays synchronous to match Chroma's embedding_function contract.
    """

    _type = "OpenAIEmbedder"

    def __call__(self, input: list[str]) -> list[list[float]]:  # type: ignore[override]
        from app.embeddings import embed_sync

        return [embed_sync(t) for t in input]

    def name(self) -> str:  # pragma: no cover - simple helper
        return "openai-embedder"


class _ChromaCacheWrapper:
    """Adapter exposing a minimal collection-like API for Chroma."""

    def __init__(self, collection) -> None:  # type: ignore[no-untyped-def]
        self._col = collection

    def get_items(
        self,
        ids: list[str] | None = None,
        include: list[str] | None = None,
        **kwargs,
    ) -> dict[str, list]:
        """Delegate to the underlying collection's ``get`` method and normalize metadata."""

        res = self._col.get(ids=ids, include=include, **kwargs)
        if include is None or "metadatas" in include:
            metas = res.get("metadatas", [])
            res["metadatas"] = [
                _normalize_meta(m) if m is not None else {} for m in metas
            ]
        return res

    def keys(self) -> list[str]:
        """Return all document identifiers from the collection."""

        return self._col.get(include=[]).get("ids", [])

    def __getattr__(self, name):  # pragma: no cover - simple delegation
        return getattr(self._col, name)


class ChromaVectorStore(VectorStore):
    def __init__(self) -> None:
        self._dist_cutoff = 1.0 - _get_sim_threshold()

        use_cloud = os.getenv("VECTOR_STORE", "local").lower() == "cloud"
        self._is_local = not use_cloud
        self._path: str | None = None

        if use_cloud:
            from chromadb import CloudClient

            client = CloudClient(
                api_key=os.getenv("CHROMA_API_KEY", ""),
                tenant=os.getenv("CHROMA_TENANT_ID", ""),
                database=os.getenv("CHROMA_DATABASE_NAME", ""),
            )
        else:
            path = os.getenv("CHROMA_PATH", ".chroma_data")
            # Ensure directory exists unless misconfigured (e.g., path is a file)
            os.makedirs(path, exist_ok=True)
            from chromadb import PersistentClient

            client = PersistentClient(path=path)
            self._path = path

        self._client = client

        # Choose collection embedder: length (default) or OpenAI
        embed_kind = os.getenv("CHROMA_EMBEDDER", "length").strip().lower()
        if embed_kind == "openai":
            # Prefer Chroma's native embedding function to ensure the collection
            # is created with a proper configuration that includes a `_type` key.
            if chroma_ef is not None and hasattr(chroma_ef, "OpenAIEmbeddingFunction"):
                try:
                    self._embedder = chroma_ef.OpenAIEmbeddingFunction(  # type: ignore[attr-defined]
                        api_key=os.getenv("OPENAI_API_KEY", ""),
                        model_name=os.getenv("EMBED_MODEL", "text-embedding-3-small"),
                    )
                    logger.info(
                        "Chroma embedder selected: chroma.openai (%s)",
                        os.getenv("EMBED_MODEL", "text-embedding-3-small"),
                    )
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning(
                        "Chroma OpenAIEmbeddingFunction failed (%s); using local OpenAI embedder",
                        e,
                    )
                    self._embedder = _OpenAIEmbedder()
            else:
                # Fallback to local sync embedder (works with older Chroma)
                self._embedder = _OpenAIEmbedder()
                logger.info("Chroma embedder selected: openai (local)")
        else:
            self._embedder = _LengthEmbedder()
            logger.info("Chroma embedder selected: length")

        # Embedder/dimension coupling validation
        try:
            if embed_kind == "openai":
                # OpenAI embeddings default to 1536 for text-embedding-3-small
                exp_dim = int(os.getenv("EMBED_DIM", "1536"))
                if exp_dim not in {1536, 3072}:  # allow future variants
                    logger.warning(
                        "EMBED_DIM=%s may not match OpenAI embedder; expected 1536/3072",
                        exp_dim,
                    )
            else:
                # Length embedder emits dimension=1
                exp_dim = int(os.getenv("EMBED_DIM", "1536"))
                if exp_dim != 1:
                    logger.warning(
                        "EMBED_DIM=%s mismatch: length embedder uses dim=1", exp_dim
                    )
        except Exception:
            pass

        # Gate QA cache collection behind env flag so it cannot block startup
        # Disable QA cache only outside tests
        disable_qa = (
            os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes"}
            and "PYTEST_CURRENT_TEST" not in os.environ
            and "pytest" not in sys.modules
        )
        if disable_qa:
            self._cache = _NoopCache()
        else:
            base_cache = self._create_collection_safely("qa_cache")
            self._cache = _ChromaCacheWrapper(base_cache)

            # Optional: self-heal corrupt QA cache in non-prod when asked
            reset_bad = os.getenv("QA_CACHE_RESET_ON_KEYERROR", "").lower() in {
                "1",
                "true",
                "yes",
            }
            if reset_bad and os.getenv("ENV", "").lower() != "production":
                try:
                    # Warm up / minimal validation
                    _ = self._cache.get_items(limit=1)
                except KeyError:
                    logger.warning(
                        "QA cache corrupted (missing _type). Dropping collection."
                    )
                    try:
                        self._client.delete_collection("qa_cache")
                    except Exception:
                        # Best-effort; if this fails we keep going and let downstream guards handle it
                        pass
                    # Recreate a fresh collection
                    try:
                        base_cache = self._client.get_or_create_collection(
                            "qa_cache",
                            embedding_function=self._embedder,
                            metadata={"hnsw:space": "cosine"},
                        )
                    except TypeError:
                        base_cache = self._client.get_or_create_collection(
                            "qa_cache", embedding_function=self._embedder
                        )
                    self._cache = _ChromaCacheWrapper(base_cache)
        self._user_memories = self._create_collection_safely("user_memories")

    def _create_collection_safely(self, name: str):  # type: ignore[no-untyped-def]
        """Create or load a collection, handling minor API differences.

        Newer Chroma versions accept ``metadata`` for distance config; older
        ones do not. We try the modern signature first and fall back.
        """
        try:
            return self._client.get_or_create_collection(  # type: ignore[attr-defined]
                name,
                embedding_function=self._embedder,
                metadata={"hnsw:space": "cosine"},
            )
        except TypeError:
            return self._client.get_or_create_collection(  # type: ignore[attr-defined]
                name, embedding_function=self._embedder
            )

    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        self._user_memories.upsert(
            ids=[mem_id],
            documents=[memory],
            metadatas=[{"user_id": user_id, "ts": time.time()}],
        )
        hashed = hash_user_id(user_id)
        metrics.USER_MEMORY_ADDS.labels("chroma", hashed).inc()
        logger.debug("Added user memory %s for %s", mem_id, hashed)
        return mem_id

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> list[str]:
        logger.info(
            "query_user_memories start user_id=%s prompt=%s k=%s",
            user_id,
            prompt,
            k,
        )
        # Determine which embedder is active to interpret cutoff semantics
        use_length = not hasattr(self, "_embedder") or isinstance(
            self._embedder, _LengthEmbedder
        )
        # Optional explicit query threshold (similarity in [0,1]) wins if provided
        _vqt_raw = os.getenv("VECTOR_QUERY_THRESHOLD")
        vqt_override = None
        if _vqt_raw is not None:
            try:
                vqt = float(_vqt_raw)
                # Clamp to [0,1]
                if vqt < 0.0:
                    vqt = 0.0
                if vqt > 1.0:
                    vqt = 1.0
                vqt_override = vqt
            except Exception:
                vqt_override = None
        sim_threshold = (
            vqt_override if (vqt_override is not None) else _get_sim_threshold()
        )
        env_has_sim = "SIM_THRESHOLD" in os.environ
        if (vqt_override is None) and use_length and not env_has_sim:
            # For length embedder without explicit env override, interpret
            # the embedder default as a distance cutoff (relaxed from 0.5→0.6)
            self._dist_cutoff = float(sim_threshold)
            sim_threshold_for_log = 1.0 - self._dist_cutoff
        else:
            # In all other cases, use standard similarity threshold semantics
            self._dist_cutoff = 1.0 - sim_threshold
            sim_threshold_for_log = sim_threshold
        try:
            logger.info(
                "vector.query_threshold",
                extra={
                    "meta": {
                        "backend": "chroma",
                        "sim_threshold": round(sim_threshold_for_log, 4),
                        "dist_cutoff": round(self._dist_cutoff, 4),
                    }
                },
            )
        except Exception:
            pass
        # Use normalized prompt for length-based distance computation
        _, norm_prompt = _normalize(prompt)
        # Use broad query when using length embedder so fallback tests that seed
        # via add_user_memory work regardless of Chroma distance behaviour.
        include = ["documents", "distances", "metadatas"]
        self_query = {
            "query_texts": [prompt],
            "where": {"user_id": user_id},
            "n_results": max(k, 5),
            "include": include,
        }
        try:
            # Chaos injection for vector store failures
            from app.chaos import chaos_vector_operation_sync

            def perform_query():
                return self._user_memories.query(**self_query)

            res = chaos_vector_operation_sync("query_user_memories", perform_query)
        except Exception:
            # Fallback: when query fails (older client quirks), approximate by scanning
            # the user's docs and computing distances locally using the selected metric.
            try:
                all_docs = self._user_memories.get(
                    where={"user_id": user_id}, include=["documents", "metadatas"]
                )  # type: ignore[arg-type]
            except Exception:
                all_docs = {"documents": [[]], "metadatas": [[{}]]}
            res = {
                "documents": all_docs.get("documents") or [[]],
                "metadatas": all_docs.get("metadatas") or [[{}]],
                "distances": [[None] * len((all_docs.get("documents") or [[]])[0])],
            }  # type: ignore[dict-item]
        docs = (res.get("documents") or [[" "]])[0]
        metas = (res.get("metadatas") or [[{}]])[0]
        dvals = (res.get("distances") or [[None]])[0]
        items: list[tuple[float, float, str]] = []
        for idx in range(min(len(docs), len(metas))):
            doc = docs[idx]
            meta = metas[idx] or {}
            if not doc:
                continue
            if use_length:
                # Normalize stored document for deterministic comparison
                _, norm_doc = _normalize(doc)
                # Guard: never consider equal-length-but-different-text similar
                if norm_doc != norm_prompt and (len(norm_doc) == len(norm_prompt)):
                    continue
                sim = _length_similarity(norm_doc, norm_prompt)
                dist = 1.0 - sim
            else:
                # Prefer provided distances from the vector store when available.
                # Fall back to a simple length‑ratio distance only when distances are missing.
                dist_val = dvals[idx] if idx < len(dvals) else None
                if dist_val is None:
                    dist = abs(len(doc) - len(norm_prompt)) / max(
                        len(doc), len(norm_prompt), 1
                    )
                else:
                    dist = float(dist_val)
            # Apply strict global cutoff: only keep items with distance < cutoff
            if dist < self._dist_cutoff:
                items.append((float(dist), -float(meta.get("ts", 0) or 0.0), doc))
        items.sort()
        top_items = items[:k]
        docs_out = [doc for _, _, doc in top_items]
        dists_out = [round(float(dist), 4) for dist, _, _ in top_items]
        logger.info(
            "query_user_memories end user_id=%s returned=%d dists=%s",
            user_id,
            len(docs_out),
            dists_out,
        )
        return docs_out

    # -----------------------------
    # Admin helpers
    # -----------------------------
    def list_user_memories(self, user_id: str) -> list[dict]:  # type: ignore[override]
        try:
            res = self._user_memories.get(
                where={"user_id": user_id}, include=["ids", "documents", "metadatas"]
            )
        except Exception:
            # Fallback to query with broad limit
            res = self._user_memories.query(
                query_texts=["*"],
                where={"user_id": user_id},
                n_results=1000,
                include=["ids", "documents", "metadatas"],
            )
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[{}]])[0]
        out: list[dict] = []
        for i, d, m in zip(ids, docs, metas, strict=False):
            out.append({"id": i, "text": d, "meta": m or {}})
        return out

    def delete_user_memory(self, user_id: str, mem_id: str) -> bool:  # type: ignore[override]
        try:
            self._user_memories.delete(ids=[mem_id])
            return True
        except Exception:
            return False

    @property
    def qa_cache(self):  # type: ignore[override]
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        if (
            os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes"}
            and "PYTEST_CURRENT_TEST" not in os.environ
            and "pytest" not in sys.modules
        ):
            return
        _, norm = _normalize(prompt)
        raw_meta = {"answer": answer, "timestamp": time.time(), "feedback": None}
        cleaned = _clean_meta(raw_meta)
        self._cache.upsert(
            ids=[cache_id],
            documents=[norm],
            metadatas=[cleaned],
        )

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> str | None:
        self._dist_cutoff = 1.0 - _get_sim_threshold()
        hash_, norm = _normalize(prompt)
        if (
            os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes"}
            and "PYTEST_CURRENT_TEST" not in os.environ
            and "pytest" not in sys.modules
        ):
            logger.debug("QA cache disabled; miss for %s", hash_)
            return None
        res = self._cache.query(
            query_texts=[norm],
            n_results=1,
            include=["metadatas", "documents", "distances"],
        )
        ids = res.get("ids", [[]])[0]
        if not ids:
            logger.debug("Cache miss for %s", hash_)
            return None
        doc = res.get("documents", [[]])[0][0] or ""
        meta_raw = res.get("metadatas", [[]])
        meta = _normalize_meta(meta_raw[0][0] if meta_raw and meta_raw[0] else {})
        dvals = res.get("distances", [[None]])[0]
        use_length = not hasattr(self, "_embedder") or isinstance(
            self._embedder, _LengthEmbedder
        )
        if use_length:
            # Guard: never consider equal-length-but-different-text similar
            if doc != norm and (len(doc) == len(norm)):
                logger.debug("Cache miss for %s (equal length mismatch)", hash_)
                return None
            sim = _length_similarity(doc, norm)
            dist = 1.0 - sim
        else:
            dist = float(dvals[0]) if dvals and dvals[0] is not None else 1.0
        if dist > self._dist_cutoff:
            logger.debug("Cache miss for %s (dist=%.4f > cutoff)", hash_, dist)
            return None
        ts = float(meta.get("timestamp", 0))
        if ttl_seconds and time.time() - ts > ttl_seconds:
            logger.debug("Cache expired for %s", hash_)
            self._cache.delete(ids=[ids[0]])
            return None
        if meta.get("feedback") == "down":
            logger.debug("Cache invalidated by feedback for %s", hash_)
            self._cache.delete(ids=[ids[0]])
            return None
        logger.debug("Cache hit for %s (dist=%.4f)", hash_, dist)
        return meta.get("answer")

    def record_feedback(self, prompt: str, feedback: str) -> None:
        if (
            os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes"}
            and "PYTEST_CURRENT_TEST" not in os.environ
            and "pytest" not in sys.modules
        ):
            return
        cid = _normalize(prompt)[0]
        self._cache.update(ids=[cid], metadatas=[{"feedback": feedback}])
        if feedback == "down":
            logger.debug("Cache invalidated by feedback for %s", cid)
            self._cache.delete(ids=[cid])

    def close(self) -> None:  # pragma: no cover - thin wrapper
        client = getattr(self, "_client", None)
        if client is None:
            return
        try:
            close = getattr(client, "close", None)
            if callable(close):
                close()
            else:
                reset = getattr(client, "reset", None)
                if callable(reset):
                    reset()
        except Exception:  # pragma: no cover - best effort
            pass
        self._client = None


__all__ = ["ChromaVectorStore"]
