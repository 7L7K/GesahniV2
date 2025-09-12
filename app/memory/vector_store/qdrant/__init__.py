from __future__ import annotations

import logging
import os
import time
import uuid
from collections import deque
from typing import Dict, List, Optional, Tuple

from app.metrics import DEPENDENCY_LATENCY_SECONDS, VECTOR_OP_LATENCY_SECONDS

from ..base import MisconfiguredStoreError, SupportsQACache

logger = logging.getLogger(__name__)


try:  # optional dependency at import time
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import (
        Distance,
        FieldCondition,
        Filter,
        HnswConfigDiff,
        MatchValue,
        PointStruct,
        SearchParams,
        VectorParams,
    )
except Exception:  # pragma: no cover - symbol shim to keep import light
    QdrantClient = None  # type: ignore
    Distance = VectorParams = PointStruct = Filter = FieldCondition = MatchValue = object  # type: ignore

# Under pytest, treat qdrant as unavailable by default to avoid external deps.
# Tests that need Qdrant can explicitly patch the adapter.
import os as _os
import sys as _sys

if ("PYTEST_CURRENT_TEST" in _os.environ) or ("pytest" in _sys.modules):
    if _os.getenv("ALLOW_QDRANT_IN_TESTS", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        QdrantClient = None  # type: ignore


def _require_qdrant():
    if QdrantClient is None:
        raise MisconfiguredStoreError("qdrant-client not installed")


# lightweight in-process metrics buffer
_VS_LAT_MS: deque[float] = deque(maxlen=50)
_LAST_ERR_TS: float | None = None


def _rec_latency_ms(start: float) -> None:
    try:
        _VS_LAT_MS.append((time.perf_counter() - start) * 1000.0)
    except Exception:
        pass


def get_stats() -> dict[str, object]:
    lat = list(_VS_LAT_MS)
    avg = sum(lat) / len(lat) if lat else 0.0
    return {
        "avg_latency_ms": round(avg, 2),
        "sample_size": len(lat),
        "last_error_ts": _LAST_ERR_TS,
    }


class _QACollection(SupportsQACache):
    def __init__(self, client: QdrantClient, name: str):  # type: ignore[name-defined]
        self.client = client
        self.name = name

    def get_items(
        self, ids: list[str] | None = None, include: list[str] | None = None
    ) -> dict[str, list]:
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
        out_ids: list[str] = []
        metadatas: list[dict] = []
        documents: list[str] = []
        for pt in res:
            out_ids.append(str(pt.id))
            payload = pt.payload or {}
            metadatas.append(
                {k: payload.get(k) for k in ("answer", "timestamp", "feedback")}
            )
            documents.append(payload.get("doc") if "documents" in include else None)
        out: dict[str, list] = {"ids": out_ids}
        if "metadatas" in include:
            out["metadatas"] = metadatas
        if "documents" in include:
            out["documents"] = documents
        return out

    def upsert(
        self, *, ids: list[str], documents: list[str], metadatas: list[dict]
    ) -> None:
        points = []
        for i, doc, meta in zip(ids, documents, metadatas, strict=False):
            payload = dict(meta or {})
            payload["doc"] = doc
            points.append(PointStruct(id=i, vector=None, payload=payload))
        self.client.upsert(collection_name=self.name, points=points)

    def delete(self, *, ids: list[str] | None = None) -> None:  # type: ignore[override]
        if not ids:
            return
        self.client.delete(collection_name=self.name, points_selector=ids)

    def update(self, *, ids: list[str], metadatas: list[dict]) -> None:  # type: ignore[override]
        # Apply per-id payload updates to avoid accidental metadata cross-application
        if not ids or not metadatas:
            return
        if len(metadatas) == 1 and len(ids) >= 1:
            # Single metadata for multiple ids: apply same payload to all ids
            self.client.set_payload(
                collection_name=self.name, points=ids, payload=metadatas[0]
            )
            return
        for i, meta in zip(ids, metadatas, strict=False):
            try:
                self.client.set_payload(
                    collection_name=self.name, points=[i], payload=meta
                )
            except Exception:
                # best-effort; continue
                pass

    def keys(self) -> list[str]:
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
        # Use secure connection
        self.client = QdrantClient(url=url, api_key=api_key)
        try:
            logger.info(
                "Vector metric: cosine (locked). Threshold policy: keep if sim>=0.75 (dist<=0.25)"
            )
        except Exception:
            pass

        # Collections: sanitize illegal characters (e.g., colon) to avoid 422
        raw_cache = os.getenv("QDRANT_QA_COLLECTION", "cache:qa")
        try:
            # Replace ':' with '_' per Qdrant naming rules
            self.cache_collection = str(raw_cache).replace(":", "_")
        except Exception:
            self.cache_collection = "cache_qa"

        # QA cache uses payload-only, but Qdrant requires vectors; use size=1 stub
        try:
            self.client.get_collection(self.cache_collection)
        except Exception:
            self.client.recreate_collection(
                collection_name=self.cache_collection,
                vectors_config=VectorParams(size=1, distance=Distance.COSINE),
            )
        # Health signal: record when we recreate to help detect drift
        try:
            import logging as _logging

            _logging.getLogger(__name__).info(
                "qdrant.bootstrap.cache_qa_collection",
                extra={"meta": {"name": self.cache_collection}},
            )
        except Exception:
            pass

        self._qa = _QACollection(self.client, self.cache_collection)

    # -------------------- Lightweight helpers --------------------
    def ping(self) -> bool:
        """Lightweight ping: call /collections to verify Qdrant is reachable.

        Returns True on success, False on any error.
        """
        try:
            # get_collections is intentionally lightweight
            self.client.get_collections()
            return True
        except Exception:
            return False

    def batch_upsert(self, collection_name: str, points: list) -> dict | None:
        """Batch upsert raw PointStructs into a collection.

        Returns a dict with operation_id and counts when available, or None on failure.
        """
        try:
            before = None
            try:
                info = self.client.get_collection(collection_name)
                before = getattr(info, "points_count", None)
            except Exception:
                before = None

            resp = self.client.upsert(collection_name=collection_name, points=points)

            after = None
            try:
                info = self.client.get_collection(collection_name)
                after = getattr(info, "points_count", None)
            except Exception:
                after = None

            # Try to extract operation id if the SDK returned one
            op_id = None
            try:
                if hasattr(resp, "operation_id"):
                    op_id = resp.operation_id
                elif isinstance(resp, dict):
                    op_id = resp.get("operation_id")
            except Exception:
                op_id = None

            try:
                logger.info(
                    "qdrant.upsert.batch",
                    extra={
                        "meta": {
                            "collection": collection_name,
                            "op_id": op_id,
                            "before": before,
                            "after": after,
                            "points_upserted": len(points),
                        }
                    },
                )
            except Exception:
                pass

            return {"operation_id": op_id, "before": before, "after": after}

        except Exception:
            global _LAST_ERR_TS
            _LAST_ERR_TS = time.time()
            logger.exception("qdrant.batch_upsert failed for %s", collection_name)
            return None

    def batch_upsert_user_memories(self, user_id: str, texts: list[str]) -> list[str]:
        """Convenience: embed a list of texts and upsert them into the user's collection.

        Returns list of inserted ids (may be shorter if some items were dropped).
        """
        from app.embeddings import embed_sync

        dim = int(os.getenv("EMBED_DIM", "1536"))
        col = self._user_collection(user_id)
        self._ensure_collection(col, dim)

        points = []
        ids: list[str] = []
        for text in texts:
            try:
                vec = embed_sync(text)
                if len(vec) != dim:
                    logger.warning(
                        "qdrant.batch_upsert_user_memories: dropping due to embed dim mismatch user=%s expected=%s got=%s",
                        user_id,
                        dim,
                        len(vec),
                    )
                    continue
                mem_id = str(uuid.uuid4())
                payload = {"user_id": user_id, "text": text, "created_at": time.time()}
                points.append(PointStruct(id=mem_id, vector=vec, payload=payload))
                ids.append(mem_id)
            except Exception:
                logger.exception("qdrant.batch_upsert_user_memories failed to embed/text=%s", text)
                continue

        if points:
            self.batch_upsert(col, points)

        return ids

    # -------------------- Bootstrap helpers --------------------
    def _ensure_collection(self, name: str, dim: int) -> None:
        t0 = time.perf_counter()
        try:
            self.client.get_collection(name)
        except Exception:
            self.client.recreate_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                hnsw_config=HnswConfigDiff(
                    m=int(os.getenv("QDRANT_HNSW_M", "32")),
                    ef_construct=int(os.getenv("QDRANT_HNSW_EF_CONSTRUCT", "128")),
                ),
            )
        else:
            # Ensure HNSW params on existing collection
            try:
                self.client.update_collection(
                    collection_name=name,
                    hnsw_config=HnswConfigDiff(
                        m=int(os.getenv("QDRANT_HNSW_M", "32")),
                        ef_construct=int(os.getenv("QDRANT_HNSW_EF_CONSTRUCT", "128")),
                    ),
                )
            except Exception:
                pass
        finally:
            try:
                DEPENDENCY_LATENCY_SECONDS.labels(
                    "qdrant", "ensure_collection"
                ).observe(time.perf_counter() - t0)
            except Exception:
                pass
        # Attempt to create useful payload indexes (best-effort)
        for field in (
            "user_id",
            "type",
            "topic",
            "created_at",
            "source_tier",
            "pinned",
        ):
            try:
                # Field schema names are client-version dependent; pass plain strings
                self.client.create_payload_index(
                    collection_name=name, field_name=field, field_schema="keyword"
                )
            except Exception:
                try:
                    # created_at/source_tier/pinned types can be numeric/bool
                    if field in {"created_at", "source_tier"}:
                        self.client.create_payload_index(
                            collection_name=name, field_name=field, field_schema="float"
                        )
                    elif field == "pinned":
                        self.client.create_payload_index(
                            collection_name=name, field_name=field, field_schema="bool"
                        )
                except Exception:
                    pass

    def _user_collection(self, user_id: str) -> str:
        # Sanitize user_id for use as a Qdrant collection name. Qdrant collection
        # names must not include characters like ':' which can cause 4xx errors.
        # Replace any non-alphanumeric or underscore/dash characters with '_'.
        try:
            import re

            safe = re.sub(r"[^A-Za-z0-9_\-]", "_", str(user_id))
            # Prefix with mem:user: to keep backward semantics but ensure valid name
            return f"mem_user_{safe}"
        except Exception:
            return f"mem_user_{user_id}"

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
            # Dimension enforcement: guard against mismatched embedding sizes
            dim = int(os.getenv("EMBED_DIM", "1536"))
            if len(vec) != dim:
                logger.warning(
                    "qdrant.add_user_memory: dropping vector due to dim mismatch user=%s expected=%s got=%s",
                    user_id,
                    dim,
                    len(vec),
                )
                return mem_id

            resp = self.client.upsert(
                collection_name=col,
                points=[PointStruct(id=mem_id, vector=vec, payload=payload)],
            )
            # Try to log operation id and point counts (best-effort)
            try:
                op_id = getattr(resp, "operation_id", None) if resp is not None else None
            except Exception:
                op_id = None
            try:
                info = self.client.get_collection(col)
                after = getattr(info, "points_count", None)
            except Exception:
                after = None
            try:
                logger.info(
                    "qdrant.upsert",
                    extra={
                        "meta": {
                            "collection": col,
                            "user_id": user_id,
                            "op_id": op_id,
                            "points_upserted": 1,
                            "after": after,
                        }
                    },
                )
            except Exception:
                pass
            try:
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "upsert").observe(
                    time.perf_counter() - t1
                )
                VECTOR_OP_LATENCY_SECONDS.labels("upsert").observe(
                    time.perf_counter() - t1
                )
            except Exception:
                pass
            return mem_id
        except Exception:
            global _LAST_ERR_TS
            _LAST_ERR_TS = time.time()
            raise
        finally:
            _rec_latency_ms(t0)

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> list[str]:
        from app.embeddings import embed_sync

        t0 = time.perf_counter()
        try:
            vec = embed_sync(prompt)
            col = self._user_collection(user_id)
            dim = int(os.getenv("EMBED_DIM", "1536"))
            self._ensure_collection(col, dim)
            try:
                flt = Filter(
                    must=[
                        FieldCondition(key="user_id", match=MatchValue(value=user_id))
                    ]
                )
            except Exception:
                flt = None  # not strictly needed with per-user collections
            t1 = time.perf_counter()
            res = self.client.search(
                collection_name=col,
                query_vector=vec,
                limit=max(k, 10),
                query_filter=flt,
                search_params=SearchParams(
                    hnsw_ef=int(os.getenv("QDRANT_SEARCH_EF", "128"))
                ),
                with_payload=True,
            )
            try:
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "search").observe(
                    time.perf_counter() - t1
                )
                VECTOR_OP_LATENCY_SECONDS.labels("search").observe(
                    time.perf_counter() - t1
                )
            except Exception:
                pass
            docs: list[tuple[float, float, str]] = []
            # Lock policy: cosine similarity must be >= 0.75 → distance <= 0.25
            cutoff = 0.25
            raw_scores: list[float] = []
            kept = dropped = 0
            for pt in res:
                payload = pt.payload or {}
                text = payload.get("text") or ""
                score = float(pt.score or 0.0)  # cosine similarity
                dist = 1.0 - score
                raw_scores.append(round(score, 4))
                if dist <= cutoff:
                    ts = float(
                        payload.get("updated_at") or payload.get("created_at") or 0.0
                    )
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

    def list_user_memories(self, user_id: str) -> list[dict]:
        col = self._user_collection(user_id)
        dim = int(os.getenv("EMBED_DIM", "1536"))
        self._ensure_collection(col, dim)
        t0 = time.perf_counter()
        try:
            t1 = time.perf_counter()
            res, _ = self.client.scroll(
                collection_name=col, with_payload=True, limit=1000
            )
            try:
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "scroll").observe(
                    time.perf_counter() - t1
                )
                VECTOR_OP_LATENCY_SECONDS.labels("scroll").observe(
                    time.perf_counter() - t1
                )
            except Exception:
                pass
        except Exception:
            global _LAST_ERR_TS
            _LAST_ERR_TS = time.time()
            raise
        finally:
            _rec_latency_ms(t0)
        out: list[dict] = []
        for pt in res:
            out.append(
                {
                    "id": str(pt.id),
                    "text": (pt.payload or {}).get("text"),
                    "meta": pt.payload or {},
                }
            )
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
                DEPENDENCY_LATENCY_SECONDS.labels("qdrant", "delete").observe(
                    time.perf_counter() - t1
                )
                VECTOR_OP_LATENCY_SECONDS.labels("delete").observe(
                    time.perf_counter() - t1
                )
            except Exception:
                pass
            return True
        except Exception:
            global _LAST_ERR_TS
            _LAST_ERR_TS = time.time()
            return False
        finally:
            _rec_latency_ms(t0)

    def drop_user_collection(self, user_id: str) -> bool:
        """Delete entire per-user collection. Returns True on success."""
        col = self._user_collection(user_id)
        try:
            self.client.delete_collection(collection_name=col)
            try:
                logger.info("qdrant.drop_collection", extra={"meta": {"collection": col, "user_id": user_id}})
            except Exception:
                pass
            return True
        except Exception:
            try:
                logger.exception("qdrant.drop_collection failed for %s", col)
            except Exception:
                pass
            return False

    def update_user_memory(self, user_id: str, mem_id: str, new_text: str) -> bool:
        """Re-embed and upsert an existing memory by id. Returns True on success."""
        from app.embeddings import embed_sync

        try:
            dim = int(os.getenv("EMBED_DIM", "1536"))
            col = self._user_collection(user_id)
            self._ensure_collection(col, dim)
            vec = embed_sync(new_text)
            if len(vec) != dim:
                logger.warning(
                    "qdrant.update_user_memory: embed dim mismatch for %s expected=%s got=%s",
                    mem_id,
                    dim,
                    len(vec),
                )
                return False
            payload = {"user_id": user_id, "text": new_text, "updated_at": time.time()}
            self.client.upsert(collection_name=col, points=[PointStruct(id=mem_id, vector=vec, payload=payload)])
            try:
                logger.info(
                    "qdrant.update_user_memory",
                    extra={"meta": {"collection": col, "user_id": user_id, "mem_id": mem_id}},
                )
            except Exception:
                pass
            return True
        except Exception:
            logger.exception("qdrant.update_user_memory failed for %s", mem_id)
            return False

    # -------------------- QA cache API -----------------------
    @property
    def qa_cache(self) -> SupportsQACache:
        return self._qa

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        if os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes", "on"}:
            return
        self._qa.upsert(
            ids=[cache_id],
            documents=[prompt],
            metadatas=[{"answer": answer, "timestamp": time.time(), "feedback": None}],
        )

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> str | None:
        if os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes", "on"}:
            return None
        # Lightweight exact-id path: treat prompts like hashes via env usage in app.memory.api
        res = self._qa.get_items(
            ids=None, include=["metadatas", "documents"]
        )  # scan small cache (<=1k)
        ids = res.get("ids", [])
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])
        best: tuple[float, str | None] = (1e9, None)
        try:
            import numpy as _np

            from app.embeddings import embed_sync

            q = embed_sync(prompt)
            for _id, d, m in zip(ids, docs, metas, strict=False):
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
        for _id, d in zip(ids, docs, strict=False):
            if d == prompt:
                try:
                    self._qa.update(ids=[_id], metadatas=[{"feedback": feedback}])
                except Exception:
                    pass
                break

    def close(self) -> None:  # pragma: no cover - no-op for HTTP client
        return None


__all__ = ["QdrantVectorStore"]
