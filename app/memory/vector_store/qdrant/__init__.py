from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple
from collections import deque

from ..base import MisconfiguredStoreError, SupportsQACache
from app.metrics import DEPENDENCY_LATENCY_SECONDS, VECTOR_OP_LATENCY_SECONDS

logger = logging.getLogger(__name__)


try:  # optional dependency at import time
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import (
        Distance,
        VectorParams,
        PointStruct,
        Filter,
        FieldCondition,
        MatchValue,
        SearchParams,
        HnswConfigDiff,
    )
except Exception:  # pragma: no cover - symbol shim to keep import light
    QdrantClient = None  # type: ignore
    Distance = VectorParams = PointStruct = Filter = FieldCondition = MatchValue = object  # type: ignore

# Under pytest, treat qdrant as unavailable by default to avoid external deps.
# Tests that need Qdrant can explicitly patch the adapter.
import os as _os
import sys as _sys
if ("PYTEST_CURRENT_TEST" in _os.environ) or ("pytest" in _sys.modules):
    if _os.getenv("ALLOW_QDRANT_IN_TESTS", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        QdrantClient = None  # type: ignore


def _require_qdrant():
    if QdrantClient is None:
        raise MisconfiguredStoreError("qdrant-client not installed")


# lightweight in-process metrics buffer
_VS_LAT_MS: "deque[float]" = deque(maxlen=50)
_LAST_ERR_TS: Optional[float] = None


def _rec_latency_ms(start: float) -> None:
    try:
        _VS_LAT_MS.append((time.perf_counter() - start) * 1000.0)
    except Exception:
        pass


def get_stats() -> Dict[str, object]:
    lat = list(_VS_LAT_MS)
    avg = sum(lat) / len(lat) if lat else 0.0
    return {
        "avg_latency_ms": round(avg, 2),
        "sample_size": len(lat),
        "last_error_ts": _LAST_ERR_TS,
    }


class _QACollection(SupportsQACache):
    def __init__(self, client: "QdrantClient", name: str):  # type: ignore[name-defined]
        self.client = client
        self.name = name

    def get_items(self, ids: List[str] | None = None, include: List[str] | None = None) -> Dict[str, List]:
        include = include or ["metadatas", "documents"]
        want_payload = ("metadatas" in include) or ("documents" in include)
        if ids:
            res = self.client.retrieve(
                collection_name=self.name,
                ids=ids,
                with_payload=want_payload,
                with_vectors=False,
            )
        else:
            # for simplicity, limit to first 1000
            res = self.client.scroll(
                collection_name=self.name,
                with_payload=want_payload,
                with_vectors=False,
                limit=1000,
            )[0]
        out_ids: List[str] = []
        metadatas: List[Dict] = []
        documents: List[str] = []
        for pt in res:
            out_ids.append(str(pt.id))
            payload = pt.payload or {}
            metadatas.append({k: payload.get(k) for k in ("answer", "timestamp", "feedback")})
            documents.append(payload.get("doc") if "documents" in include else None)
        out: Dict[str, List] = {"ids": out_ids}
        if "metadatas" in include:
            out["metadatas"] = metadatas
        if "documents" in include:
            out["documents"] = documents
        return out

    def upsert(self, *, ids: List[str], documents: List[str], metadatas: List[Dict]) -> None:
        points = []
        for i, doc, meta in zip(ids, documents, metadatas):
            payload = dict(meta or {})
            payload["doc"] = doc
            points.append(PointStruct(id=i, vector=None, payload=payload))
        self.client.upsert(collection_name=self.name, points=points)

    def delete(self, *, ids: List[str] | None = None) -> None:  # type: ignore[override]
        if not ids:
            return
        self.client.delete(collection_name=self.name, points_selector=ids)

    def update(self, *, ids: List[str], metadatas: List[Dict]) -> None:  # type: ignore[override]
        # Apply per-id payload updates to avoid accidental metadata cross-application
        if not ids or not metadatas:
            return
        if len(metadatas) == 1 and len(ids) >= 1:
            # Single metadata for multiple ids: apply same payload to all ids
            self.client.set_payload(collection_name=self.name, points=ids, payload=metadatas[0])
            return
        for i, meta in zip(ids, metadatas):
            try:
                self.client.set_payload(collection_name=self.name, points=[i], payload=meta)
            except Exception:
                # best-effort; continue
                pass

    def keys(self) -> List[str]:
        res = self.client.scroll(
            collection_name=self.name, with_payload=False, limit=1000
        )[0]
        return [str(p.id) for p in res]


class QdrantVectorStore:
    """Thin adapter to Qdrant for user memories + lightweight QA cache."""

    def __init__(self) -> None:
        _require_qdrant()
        url = os.getenv("QDRANT_URL") or "http://localhost:6333"
        api_key = os.getenv("QDRANT_API_KEY") or None
        self.client = QdrantClient(url=url, api_key=api_key)
        try:
            logger.info("Vector metric: cosine (locked). Threshold policy: keep if sim>=0.75 (dist<=0.25)")
        except Exception:
            pass

        # Collections
        self.cache_collection = os.getenv("QDRANT_QA_COLLECTION", "cache:qa")

        # QA cache uses payload-only, but Qdrant requires vectors; use size=1 stub
        try:
            self.client.get_collection(self.cache_collection)
        except Exception:
            self.client.recreate_collection(
                collection_name=self.cache_collection,
                vectors_config=VectorParams(size=1, distance=Distance.COSINE),
            )

        self._qa = _QACollection(self.client, self.cache_collection)

    # -------------------- Bootstrap helpers --------------------
    def _ensure_collection(self, name: str, dim: int) -> None:
        t0 = time.perf_counter()
        try:
            self.client.get_collection(name)
        except Exception:
            self.client.recreate_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                hnsw_config=HnswConfigDiff(m=int(os.getenv("QDRANT_HNSW_M", "32")), ef_construct=int(os.getenv("QDRANT_HNSW_EF_CONSTRUCT", "128"))),
            )
        else:
            # Ensure HNSW params on existing collection
            try:
                self.client.update_collection(
                    collection_name=name,
                    hnsw_config=HnswConfigDiff(m=int(os.getenv("QDRANT_HNSW_M", "32")), ef_construct=int(os.getenv("QDRANT_HNSW_EF_CONSTRUCT", "128"))),
                )
            except Exception:
                pass
        finally:
            try:
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "ensure_collection").observe(time.perf_counter() - t0)
            except Exception:
                pass
        # Attempt to create useful payload indexes (best-effort)
        for field in ("user_id", "type", "topic", "created_at", "source_tier", "pinned"):
            try:
                # Field schema names are client-version dependent; pass plain strings
                self.client.create_payload_index(collection_name=name, field_name=field, field_schema="keyword")
            except Exception:
                try:
                    # created_at/source_tier/pinned types can be numeric/bool
                    if field in {"created_at", "source_tier"}:
                        self.client.create_payload_index(collection_name=name, field_name=field, field_schema="float")
                    elif field == "pinned":
                        self.client.create_payload_index(collection_name=name, field_name=field, field_schema="bool")
                except Exception:
                    pass

    def _user_collection(self, user_id: str) -> str:
        return f"mem:user:{user_id}"

    # -------------------- User memory API --------------------
    def add_user_memory(self, user_id: str, memory: str) -> str:
        from app.embeddings import embed_sync
        t0 = time.perf_counter()
        try:
            dim = int(os.getenv("EMBED_DIM", "1536"))
            col = self._user_collection(user_id)
            self._ensure_collection(col, dim)
            vec = embed_sync(memory)
            mem_id = str(uuid.uuid4())
            checksum = __import__("hashlib").sha256(memory.encode("utf-8")).hexdigest()
            now = time.time()
            payload = {
                # Identifiers
                "user_id": user_id,
                "doc_id": mem_id,
                "source": "memgpt",
                "namespace": "mem:user",
                # Classification
                "type": "note",
                "topic": None,
                "entities": [],
                # Trust & quality
                "confidence": 0.7,
                "quality": 0.5,
                "source_tier": 2,
                # Time & lifecycle
                "created_at": now,
                "updated_at": now,
                "decay_at": None,
                "pinned": False,
                # Governance
                "evidence_ids": [],
                "checksum": checksum,
                "redactions": [],
                # Raw text
                "text": memory,
            }
            t1 = time.perf_counter()
            self.client.upsert(
                collection_name=col,
                points=[PointStruct(id=mem_id, vector=vec, payload=payload)],
            )
            try:
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "upsert").observe(time.perf_counter() - t1)
                VECTOR_OP_LATENCY_SECONDS.labels("upsert").observe(time.perf_counter() - t1)
            except Exception:
                pass
            return mem_id
        except Exception:
            global _LAST_ERR_TS
            _LAST_ERR_TS = time.time()
            raise
        finally:
            _rec_latency_ms(t0)

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
        from app.embeddings import embed_sync

        t0 = time.perf_counter()
        try:
            vec = embed_sync(prompt)
            col = self._user_collection(user_id)
            dim = int(os.getenv("EMBED_DIM", "1536"))
            self._ensure_collection(col, dim)
            try:
                flt = Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])
            except Exception:
                flt = None  # not strictly needed with per-user collections
            t1 = time.perf_counter()
            res = self.client.search(
                collection_name=col,
                query_vector=vec,
                limit=max(k, 10),
                query_filter=flt,
                search_params=SearchParams(hnsw_ef=int(os.getenv("QDRANT_SEARCH_EF", "128"))),
                with_payload=True,
            )
            try:
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "search").observe(time.perf_counter() - t1)
                VECTOR_OP_LATENCY_SECONDS.labels("search").observe(time.perf_counter() - t1)
            except Exception:
                pass
            docs: List[Tuple[float, float, str]] = []
            # Lock policy: cosine similarity must be >= 0.75 → distance <= 0.25
            cutoff = 0.25
            raw_scores: List[float] = []
            kept = dropped = 0
            for pt in res:
                payload = pt.payload or {}
                text = payload.get("text") or ""
                score = float(pt.score or 0.0)  # cosine similarity
                dist = 1.0 - score
                raw_scores.append(round(score, 4))
                if dist <= cutoff:
                    ts = float(payload.get("updated_at") or payload.get("created_at") or 0.0)
                    docs.append((dist, -ts, text))
                    kept += 1
                else:
                    dropped += 1
            docs.sort()
            try:
                logger.info(
                    "qdrant.read user=%s scores=%s threshold=sim>=0.75 kept=%d dropped=%d",
                    user_id,
                    raw_scores[:5],
                    kept,
                    dropped,
                )
            except Exception:
                pass
            return [d for _, __, d in docs[:k]]
        except Exception:
            global _LAST_ERR_TS
            _LAST_ERR_TS = time.time()
            raise
        finally:
            _rec_latency_ms(t0)

    def list_user_memories(self, user_id: str) -> List[Dict]:
        col = self._user_collection(user_id)
        dim = int(os.getenv("EMBED_DIM", "1536"))
        self._ensure_collection(col, dim)
        t0 = time.perf_counter()
        try:
            t1 = time.perf_counter()
            res, _ = self.client.scroll(collection_name=col, with_payload=True, limit=1000)
            try:
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "scroll").observe(time.perf_counter() - t1)
                VECTOR_OP_LATENCY_SECONDS.labels("scroll").observe(time.perf_counter() - t1)
            except Exception:
                pass
        except Exception:
            global _LAST_ERR_TS
            _LAST_ERR_TS = time.time()
            raise
        finally:
            _rec_latency_ms(t0)
        out: List[Dict] = []
        for pt in res:
            out.append({"id": str(pt.id), "text": (pt.payload or {}).get("text"), "meta": pt.payload or {}})
        return out

    def delete_user_memory(self, user_id: str, mem_id: str) -> bool:
        t0 = time.perf_counter()
        try:
            col = self._user_collection(user_id)
            dim = int(os.getenv("EMBED_DIM", "1536"))
            self._ensure_collection(col, dim)
            t1 = time.perf_counter()
            self.client.delete(collection_name=col, points_selector=[mem_id])
            try:
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "delete").observe(time.perf_counter() - t1)
                VECTOR_OP_LATENCY_SECONDS.labels("delete").observe(time.perf_counter() - t1)
            except Exception:
                pass
            return True
        except Exception:
            global _LAST_ERR_TS
            _LAST_ERR_TS = time.time()
            return False
        finally:
            _rec_latency_ms(t0)

    # -------------------- QA cache API -----------------------
    @property
    def qa_cache(self) -> SupportsQACache:
        return self._qa

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        self._qa.upsert(ids=[cache_id], documents=[prompt], metadatas=[{"answer": answer, "timestamp": time.time(), "feedback": None}])

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
        # Lightweight exact-id path: treat prompts like hashes via env usage in app.memory.api
        res = self._qa.get_items(ids=None, include=["metadatas", "documents"])  # scan small cache (<=1k)
        ids = res.get("ids", [])
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])
        best: tuple[float, Optional[str]] = (1e9, None)
        try:
            from app.embeddings import embed_sync
            import numpy as _np
            q = embed_sync(prompt)
            for _id, d, m in zip(ids, docs, metas):
                if not isinstance(d, str):
                    continue
                v = embed_sync(d)
                # simple cosine distance
                num = float(_np.dot(q, v))
                den = float((_np.linalg.norm(q) * _np.linalg.norm(v)) or 1.0)
                dist = 1.0 - (num / den)
                ts = float((m or {}).get("timestamp", 0.0) or 0.0)
                if ttl_seconds and ts and (time.time() - ts > ttl_seconds):
                    continue
                if dist < best[0]:
                    best = (dist, (m or {}).get("answer"))
        except Exception:
            return None
        return best[1]

    def record_feedback(self, prompt: str, feedback: str) -> None:
        # Best-effort: look up by latest matching doc equality
        res = self._qa.get_items(ids=None, include=["metadatas", "documents"])  # type: ignore[arg-type]
        ids = res.get("ids", [])
        docs = res.get("documents", [])
        for _id, d in zip(ids, docs):
            if d == prompt:
                try:
                    self._qa.update(ids=[_id], metadatas=[{"feedback": feedback}])
                except Exception:
                    pass
                break

    def close(self) -> None:  # pragma: no cover - no-op for HTTP client
        return None


__all__ = ["QdrantVectorStore"]


