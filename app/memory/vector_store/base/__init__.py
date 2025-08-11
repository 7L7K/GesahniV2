"""Base interfaces and common errors for vector-store backends.

This module purposely keeps only abstract protocols and light exceptions so
it can be imported by any backend without causing heavy side‑effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, runtime_checkable


class VectorStoreError(RuntimeError):
    """Generic vector store error wrapper."""


class MisconfiguredStoreError(VectorStoreError):
    """Raised when a backend is not properly configured for the environment."""


@runtime_checkable
class SupportsQACache(Protocol):
    def get_items(
        self, ids: List[str] | None = None, include: List[str] | None = None
    ) -> Dict[str, List]:
        ...

    def upsert(
        self,
        *,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict],
    ) -> None:
        ...

    def delete(self, *, ids: List[str] | None = None) -> None:
        ...

    def update(self, *, ids: List[str], metadatas: List[Dict]) -> None:
        ...

    def keys(self) -> List[str]:
        ...


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """A minimal protocol shared by all vector store backends.

    Existing concrete classes (e.g., ``MemoryVectorStore`` and ``ChromaVectorStore``)
    already satisfy this protocol and do not need to inherit from it explicitly.
    """

    # User memory operations -------------------------------------------------
    def add_user_memory(self, user_id: str, memory: str) -> str: ...

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]: ...

    def list_user_memories(self, user_id: str) -> List[Dict]: ...

    def delete_user_memory(self, user_id: str, mem_id: str) -> bool: ...

    # QA cache ---------------------------------------------------------------
    @property
    def qa_cache(self) -> SupportsQACache: ...

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None: ...

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]: ...

    def record_feedback(self, prompt: str, feedback: str) -> None: ...

    # Lifecycle --------------------------------------------------------------
    def close(self) -> None: ...


@dataclass
class ScoredDocument:
    """Common document-score carrier for reranking and pipelines."""

    text: str
    score: float
    meta: Dict[str, object] | None = None


__all__ = [
    "VectorStoreError",
    "MisconfiguredStoreError",
    "SupportsQACache",
    "VectorStoreProtocol",
    "ScoredDocument",
]


