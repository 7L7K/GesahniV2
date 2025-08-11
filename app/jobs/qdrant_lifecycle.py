from __future__ import annotations

import os
import time
from typing import Dict

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


