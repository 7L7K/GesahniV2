from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _lazy_markitdown():  # pragma: no cover - optional heavy dep
    try:
        from markitdown import MarkItDown  # type: ignore
        return MarkItDown
    except Exception as e:  # pragma: no cover
        raise RuntimeError("markitdown is not installed. Run: pip install 'markitdown[all]'") from e


def _lazy_qdrant():  # pragma: no cover - optional heavy dep
    try:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.http.models import (
            Distance,
            FieldCondition,
            Filter,
            MatchValue,
            PointStruct,
            VectorParams,
        )
        return QdrantClient, Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
    except Exception as e:  # pragma: no cover
        raise RuntimeError("qdrant-client not installed") from e


def _sanitize_collection_name(name: str) -> str:
    """Return a Qdrant-safe collection name by replacing disallowed chars.

    Qdrant collection names must not contain ':' and similar path-delimiter
    characters. We conservatively allow [a-zA-Z0-9_.-] and replace others with '_'.
    """
    import re

    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


def _ensure_collection(c, name: str, dim: int) -> None:
    QdrantClient, Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue = _lazy_qdrant()  # noqa: N816
    safe = _sanitize_collection_name(name)
    backend = os.getenv("EMBEDDING_BACKEND", "openai").lower()
    # In test/stub mode, drop+create to match stub vector size and avoid dim mismatches
    if backend == "stub":
        try:
            c.delete_collection(collection_name=safe)
        except Exception:
            pass
        c.create_collection(collection_name=safe, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
    else:
        try:
            # If exists, leave as-is; otherwise create
            c.get_collection(safe)
        except Exception:
            c.recreate_collection(collection_name=safe, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
    # Helpful payload indexes (best-effort)
    for field in ("user_id", "type", "source", "created_at", "doc_hash"):
        try:
            c.create_payload_index(collection_name=safe, field_name=field, field_schema="keyword")
        except Exception:
            try:
                if field in {"created_at"}:
                    c.create_payload_index(collection_name=safe, field_name=field, field_schema="float")
            except Exception:
                pass


def _split_markdown(text: str, max_tokens: int = 800) -> tuple[list[str], list[str]]:
    """Split Markdown by headers and lightly enforce a token budget.

    Returns (chunks, top_headings).
    """
    from app.token_utils import count_tokens

    lines = text.splitlines()
    chunks: list[str] = []
    buf: list[str] = []
    headings: list[str] = []
    for line in lines:
        if line.startswith("#"):
            if buf:
                chunks.append("\n".join(buf).strip())
                buf = []
            headings.append(line.strip())
        buf.append(line)
    if buf:
        chunks.append("\n".join(buf).strip())

    # Enforce token budget by splitting large chunks on blank lines
    final: list[str] = []
    for ch in chunks:
        if count_tokens(ch) <= max_tokens:
            final.append(ch)
            continue
        paras = ch.split("\n\n")
        acc: list[str] = []
        for p in paras:
            acc.append(p)
            if count_tokens("\n\n".join(acc)) >= max_tokens:
                final.append("\n\n".join(acc).strip())
                acc = []
        if acc:
            final.append("\n\n".join(acc).strip())
    # Normalize headings (strip #/space)
    heads = [h.lstrip("# ").strip() for h in headings[:10]]
    return [f for f in final if f], heads


def _embed_many(texts: list[str]) -> list[list[float]]:
    from app.embeddings import embed_sync

    return [embed_sync(t) for t in texts]


def _qdrant_client():
    QdrantClient, *_ = _lazy_qdrant()
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"), api_key=os.getenv("QDRANT_API_KEY", ""))


def _dedup_exists(c, collection: str, doc_hash: str) -> bool:
    """Return True if a point with payload doc_hash already exists."""
    try:
        *_x, Filter, FieldCondition, MatchValue = _lazy_qdrant()
    except Exception:
        Filter = FieldCondition = MatchValue = None  # type: ignore
    try:
        flt = None
        try:
            if Filter and FieldCondition and MatchValue:
                flt = Filter(must=[FieldCondition(key="doc_hash", match=MatchValue(value=doc_hash))])
        except Exception:
            flt = None
        if flt is not None:
            res = c.scroll(collection_name=collection, limit=1, with_payload=True, with_vectors=False, scroll_filter=flt)
        else:
            res = c.scroll(collection_name=collection, limit=1)
        # Some stubs may return just a list
        if isinstance(res, tuple):
            pts, _ = res
        else:
            pts = res
        return bool(pts)
    except Exception:
        return False


def _now() -> float:
    return time.time()


def ingest_markdown_text(
    *,
    user_id: str,
    text: str,
    source: str,
    collection: str = "mem_documents",
) -> dict[str, Any]:
    """Ingest a Markdown string into Qdrant as semantic chunks.

    Returns details: {doc_hash, chunk_count, ids, headings}.
    """
    # Short-circuit entirely in stub backend to avoid network I/O in unit tests
    if os.getenv("EMBEDDING_BACKEND", "openai").lower() == "stub":
        chunks, headings = _split_markdown(text)
        doc_hash = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
        return {"status": "skipped", "doc_hash": doc_hash, "chunk_count": 0, "ids": [], "headings": headings}

    c = _qdrant_client()
    doc_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Split and embed first so we can discover vector dimension dynamically
    chunks, headings = _split_markdown(text)
    vecs = _embed_many(chunks)
    # Respect detected vector length to avoid dim mismatch during tests/mocks
    dim = len(vecs[0]) if vecs else int(os.getenv("EMBED_DIM", "1536"))

    # Ensure collection exists (sanitize name for compatibility)
    _ensure_collection(c, collection, dim)
    collection = _sanitize_collection_name(collection)

    # Dedup after ensuring collection (best‑effort)
    if _dedup_exists(c, collection, doc_hash):
        logger.info("ingest.dedup", extra={"meta": {"source": source, "collection": collection}})
        return {"status": "skipped", "doc_hash": doc_hash, "chunk_count": 0, "ids": [], "headings": []}

    # Upsert points
    try:
        QdrantClient, Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue = _lazy_qdrant()  # noqa: N816
    except Exception:
        PointStruct = None  # type: ignore

    created = _now()
    ids: list[str] = []
    points: list[Any] = []
    for i, (chunk, vec) in enumerate(zip(chunks, vecs, strict=False)):
        # Qdrant requires point ids to be unsigned integers or UUID strings.
        # Use a deterministic UUIDv5 derived from the doc_hash and chunk index.
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_hash}:{i}"))
        ids.append(pid)
        chash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
        section_path = None
        # derive section_path from headings order if possible
        if headings:
            section_path = " / ".join(headings[: min(i + 1, len(headings))])
        payload = {
            "user_id": user_id,
            "type": "doc",
            "source": source,
            "section_path": section_path or "",
            "created_at": created,
            "ingested_at": created,
            "priority": 0.0,
            "strength": 1.0,
            "tags": [],
            "hash": chash,
            "doc_id": doc_hash,
            "doc_version": 1,
            "doc_hash": doc_hash,
            "text": chunk,
        }
        if PointStruct is not None:
            points.append(PointStruct(id=pid, vector=vec, payload=payload))
        else:  # pragma: no cover - fallback
            points.append({"id": pid, "vector": vec, "payload": payload})

    c.upsert(collection_name=collection, points=points)
    logger.info("ingest.upsert", extra={"meta": {"count": len(points), "collection": collection}})
    return {
        "status": "ok",
        "doc_hash": doc_hash,
        "chunk_count": len(points),
        "ids": ids[:10],
        "headings": headings,
    }


def ingest_path_or_url(
    *,
    user_id: str,
    source: str,
    path: str | None = None,
    url: str | None = None,
    collection: str = "mem_documents",
) -> dict[str, Any]:
    """Convert a file or URL to Markdown using MarkItDown, then ingest."""
    MarkItDown = _lazy_markitdown()
    md = MarkItDown()
    target = path or url
    if not target:
        raise ValueError("path or url is required")
    res = md.convert(target)
    text: str = getattr(res, "text_content", None) or getattr(res, "text", None) or ""
    if not text:
        raise RuntimeError("MarkItDown returned empty content")
    return ingest_markdown_text(user_id=user_id, text=text, source=source or (url or path or "unknown"), collection=collection)


__all__ = ["ingest_path_or_url", "ingest_markdown_text"]


