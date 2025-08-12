from __future__ import annotations

import os
import time
from typing import Any, Dict

try:  # pragma: no cover - optional dependency
    from qdrant_client import QdrantClient
except Exception:  # pragma: no cover
    QdrantClient = None  # type: ignore


def _client() -> "QdrantClient":  # type: ignore[name-defined]
    if QdrantClient is None:
        raise RuntimeError("qdrant-client not installed")
    return QdrantClient(url=os.getenv("QDRANT_URL", ""), api_key=os.getenv("QDRANT_API_KEY", ""))


def bootstrap_collection(name: str, dim: int = 1536) -> Dict[str, str]:
    c = _client()
    try:
        c.get_collection(name)
        exists = True
    except Exception:
        exists = False
        from qdrant_client.http.models import Distance, VectorParams

        c.recreate_collection(collection_name=name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
    # Ensure payload indexes
    for field, schema in (
        ("user_id", "keyword"),
        ("type", "keyword"),
        ("topic", "keyword"),
        ("created_at", "float"),
        ("source_tier", "float"),
        ("pinned", "bool"),
    ):
        try:
            c.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
        except Exception:
            pass
    return {"status": "ok", "collection": name, "existed": str(exists)}


def collection_stats(name: str) -> Dict[str, float | int | str]:
    c = _client()
    info = c.get_collection(name)
    # qdrant-client returns pydantic models; pick some basics
    vectors_count = getattr(getattr(info, "vectors_count", None), "total", None) or 0
    points_count = getattr(getattr(info, "points_count", None), "total", None) or 0
    return {
        "collection": name,
        "vectors_count": int(vectors_count),
        "points_count": int(points_count),
    }


def purge_soft_deleted(name: str, older_than_seconds: int = 14 * 24 * 3600) -> Dict[str, int]:
    c = _client()
    # Qdrant purging of deleted points is not a separate API; we can compact by snapshot+restore or rely on server-side compaction.
    # Here we only return a stub; production purge could execute via snapshots.
    return {"purged": 0}


def upsert_versioned_chunk(
    *,
    collection: str,
    point_id: str,
    vector: list[float],
    payload: Dict[str, Any],
) -> bool:
    """Upsert with hash dedup and doc_version soft-retire policy."""
    try:
        c = _client()
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue, PointStruct
        # dedup by content hash
        h = payload.get("hash")
        if h:
            try:
                flt = Filter(must=[FieldCondition(key="hash", match=MatchValue(value=h))])
                pts, _ = c.scroll(collection_name=collection, with_payload=True, limit=1, scroll_filter=flt)
                if pts:
                    return True
            except Exception:
                pass
        # versioning: retire older doc_version for doc_id
        doc_id = payload.get("doc_id")
        version = float(payload.get("doc_version") or 1)
        if doc_id:
            try:
                flt2 = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
                pts_all, _ = c.scroll(collection_name=collection, with_payload=True, limit=10000, scroll_filter=flt2)
                max_v = 0.0
                for p in pts_all:
                    pv = float((p.payload or {}).get("doc_version") or 0)
                    if pv > max_v:
                        max_v = pv
                if version > max_v and pts_all:
                    for p in pts_all:
                        try:
                            c.set_payload(collection_name=collection, points=[p.id], payload={"pinned": False, "decay_at": float(time.time() - 1)})
                        except Exception:
                            pass
            except Exception:
                pass
        c.upsert(collection_name=collection, points=[PointStruct(id=point_id, vector=vector, payload=payload)])
        return True
    except Exception:
        return False

