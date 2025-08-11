from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from ..base import SupportsQACache

logger = logging.getLogger(__name__)


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


class _DualQACache(SupportsQACache):
    """QA cache facade that prefers Qdrant but can fall back to Chroma.

    Writes go to Qdrant. When ``VECTOR_DUAL_QA_WRITE_BOTH`` is truthy, they
    also go to Chroma for easy rollback.
    """

    def __init__(self, primary: SupportsQACache, fallback: SupportsQACache | None) -> None:
        self.primary = primary
        self.fallback = fallback

    def get_items(self, ids: List[str] | None = None, include: List[str] | None = None) -> Dict[str, List]:
        try:
            res = self.primary.get_items(ids=ids, include=include)
        except Exception:
            res = {"ids": []}
        # If a specific id lookup returned empty, try fallback for that use case
        if ids and (not res.get("ids")) and self.fallback is not None:
            try:
                return self.fallback.get_items(ids=ids, include=include)
            except Exception:
                pass
        return res

    def upsert(self, *, ids: List[str], documents: List[str], metadatas: List[Dict]) -> None:
        self.primary.upsert(ids=ids, documents=documents, metadatas=metadatas)
        if self.fallback is not None and _flag("VECTOR_DUAL_QA_WRITE_BOTH"):
            try:
                self.fallback.upsert(ids=ids, documents=documents, metadatas=metadatas)
            except Exception:
                logger.warning("Dual QA upsert to fallback failed", exc_info=True)

    def delete(self, *, ids: List[str] | None = None) -> None:  # type: ignore[override]
        try:
            self.primary.delete(ids=ids)
        finally:
            if self.fallback is not None:
                try:
                    self.fallback.delete(ids=ids)
                except Exception:
                    pass

    def update(self, *, ids: List[str], metadatas: List[Dict]) -> None:  # type: ignore[override]
        try:
            self.primary.update(ids=ids, metadatas=metadatas)
        finally:
            if self.fallback is not None:
                try:
                    self.fallback.update(ids=ids, metadatas=metadatas)
                except Exception:
                    pass

    def keys(self) -> List[str]:
        try:
            return self.primary.keys()
        except Exception:
            if self.fallback is not None:
                try:
                    return self.fallback.keys()
                except Exception:
                    pass
            return []


class DualReadVectorStore:
    """Vector store that reads from Qdrant first and falls back to Chroma.

    - Writes go to Qdrant by default. When ``VECTOR_DUAL_WRITE_BOTH`` is set,
      writes are mirrored to Chroma as best‑effort.
    - QA cache lookups are served by a wrapper that tries Qdrant first and then
      falls back to Chroma when a specific id is missing.
    """

    def __init__(self) -> None:
        # Import backends lazily to avoid hard deps at import time
        try:  # primary
            from app.memory.vector_store.qdrant import QdrantVectorStore  # type: ignore
        except Exception as e:  # pragma: no cover - optional dep guard
            raise RuntimeError("DualReadVectorStore requires qdrant-client installed") from e

        self._primary = QdrantVectorStore()  # type: ignore[no-redef]

        try:  # fallback
            from app.memory.chroma_store import ChromaVectorStore  # type: ignore
        except Exception as e:  # pragma: no cover - optional
            logger.warning("Chroma fallback unavailable: %s", e)
            self._fallback = None
        else:
            try:
                self._fallback = ChromaVectorStore()
            except Exception as e:  # pragma: no cover - tolerate init issues
                logger.warning("Chroma fallback init failed: %s", e)
                self._fallback = None

        # Compose QA cache
        fb_cache = self._fallback.qa_cache if self._fallback is not None else None
        self._qa = _DualQACache(self._primary.qa_cache, fb_cache)

    # -------------------- User memory API --------------------
    def add_user_memory(self, user_id: str, memory: str) -> str:
        mid = self._primary.add_user_memory(user_id, memory)
        if self._fallback is not None and _flag("VECTOR_DUAL_WRITE_BOTH"):
            try:
                self._fallback.add_user_memory(user_id, memory)
            except Exception:
                logger.warning("Dual add_user_memory fallback write failed", exc_info=True)
        return mid

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
        try:
            res = self._primary.query_user_memories(user_id, prompt, k)
        except Exception:
            res = []
        if (not res) and self._fallback is not None:
            try:
                fb = self._fallback.query_user_memories(user_id, prompt, k)
            except Exception:
                fb = []
            if fb:
                try:
                    from app import metrics  # lazy
                    metrics.VECTOR_FALLBACK_READS.labels("memory").inc()
                except Exception:
                    pass
                return fb
        return res

    def list_user_memories(self, user_id: str) -> List[Dict]:
        try:
            return self._primary.list_user_memories(user_id)
        except Exception:
            if self._fallback is not None:
                try:
                    return self._fallback.list_user_memories(user_id)
                except Exception:
                    pass
            return []

    def delete_user_memory(self, user_id: str, mem_id: str) -> bool:
        ok = False
        try:
            ok = self._primary.delete_user_memory(user_id, mem_id)
        finally:
            if self._fallback is not None:
                try:
                    self._fallback.delete_user_memory(user_id, mem_id)
                except Exception:
                    pass
        return ok

    # -------------------- QA cache API -----------------------
    @property
    def qa_cache(self) -> SupportsQACache:
        return self._qa

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        self._primary.cache_answer(cache_id, prompt, answer)
        if self._fallback is not None and _flag("VECTOR_DUAL_QA_WRITE_BOTH"):
            try:
                self._fallback.cache_answer(cache_id, prompt, answer)
            except Exception:
                logger.warning("Dual cache_answer fallback write failed", exc_info=True)

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
        try:
            ans = self._primary.lookup_cached_answer(prompt, ttl_seconds)
        except Exception:
            ans = None
        if ans is None and self._fallback is not None:
            try:
                fb = self._fallback.lookup_cached_answer(prompt, ttl_seconds)
                if fb is not None:
                    try:
                        from app import metrics  # lazy
                        metrics.VECTOR_FALLBACK_READS.labels("qa").inc()
                    except Exception:
                        pass
                return fb
            except Exception:
                return None
        return ans

    def record_feedback(self, prompt: str, feedback: str) -> None:
        try:
            self._primary.record_feedback(prompt, feedback)
        finally:
            if self._fallback is not None:
                try:
                    self._fallback.record_feedback(prompt, feedback)
                except Exception:
                    pass

    # -------------------- Lifecycle --------------------------
    def close(self) -> None:
        try:
            self._primary.close()
        finally:
            if self._fallback is not None:
                try:
                    self._fallback.close()
                except Exception:
                    pass


__all__ = ["DualReadVectorStore"]


