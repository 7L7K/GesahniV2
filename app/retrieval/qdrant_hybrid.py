from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

try:  # pragma: no cover - optional dependency
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue
except Exception:  # pragma: no cover
    QdrantClient = None  # type: ignore
    Filter = FieldCondition = MatchValue = object  # type: ignore

from .utils import RetrievedItem


def _client() -> "QdrantClient":  # type: ignore[name-defined]
    if QdrantClient is None:
        raise RuntimeError("qdrant-client not installed")
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"), api_key=os.getenv("QDRANT_API_KEY", ""))


def _payload_filter(user_id: str, extra: Dict[str, Any] | None = None) -> Any:
    # Minimal filter by user; allow extra key=value constraints
    conditions: List[Any] = [
        FieldCondition(key="user_id", match=MatchValue(value=user_id))  # type: ignore[arg-type]
    ]
    for k, v in (extra or {}).items():
        conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))  # type: ignore[arg-type]
    return Filter(must=conditions)  # type: ignore[call-arg]


def _to_items(points: List[Any]) -> List[RetrievedItem]:
    items: List[RetrievedItem] = []
    for p in points or []:
        pid = getattr(p, "id", None)
        payload = getattr(p, "payload", {}) or {}
        score = float(getattr(p, "score", 0.0) or 0.0)  # cosine similarity
        text = payload.get("text") or payload.get("document") or ""
        if pid is None:
            pid = payload.get("_id") or payload.get("hash") or str(hash(text))
        items.append(
            RetrievedItem(
                id=str(pid),
                text=str(text),
                score=score,
                metadata={
                    "created_at": payload.get("created_at"),
                    "source_tier": payload.get("source_tier"),
                    "pinned": bool(payload.get("pinned", False)),
                    "type": payload.get("type"),
                    "topic": payload.get("topic"),
                    **payload,
                },
            )
        )
    return items


def dense_search(
    *,
    collection: str,
    user_id: str,
    query_vector: List[float],
    limit: int,
    extra_filter: Dict[str, Any] | None = None,
) -> List[RetrievedItem]:
    c = _client()
    f = _payload_filter(user_id, extra_filter)
    res = c.search(collection_name=collection, query_vector=query_vector, limit=limit, query_filter=f)
    items = _to_items(res)
    # Enforce keep threshold sim>=0.75 (dist<=0.25)
    kept = [it for it in items if (1.0 - float(it.score)) <= 0.25]
    return kept


def sparse_search(
    *,
    collection: str,
    user_id: str,
    query: str,
    limit: int,
    extra_filter: Dict[str, Any] | None = None,
) -> List[RetrievedItem]:
    """Sparse search using Qdrant's full-text/BM25-like payload index via recommend/search points.

    We implement a simple text-match using query_text with fulltext index; if unavailable,
    return an empty list gracefully.
    """

    c = _client()
    try:
        # Prefer the dedicated text search API when available (qdrant >= 1.7)
        f = _payload_filter(user_id, extra_filter)
        res = c.search(collection_name=collection, query_text=query, limit=limit, query_filter=f)
        return _to_items(res)
    except Exception:
        return []


__all__ = ["dense_search", "sparse_search"]


