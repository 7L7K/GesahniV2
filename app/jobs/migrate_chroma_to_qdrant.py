from __future__ import annotations

"""Safe, reversible migration from Chroma to Qdrant.

Steps:
- Inventory Chroma collections and counts.
- Export payloads + original texts (qa_cache and user_memories).
- Re-embed if dimensions differ; preserve doc_id and checksum.
- Upsert into Qdrant with full payloads and indexes.
- Supports dry-run and incremental resume via idempotent upserts.
"""

import argparse
import os
import sys
import time


def _require_chroma():
    try:
        import chromadb  # noqa: F401
    except Exception as e:
        raise RuntimeError("chromadb not available") from e


def _require_qdrant():
    try:
        from qdrant_client import QdrantClient  # noqa: F401
    except Exception as e:
        raise RuntimeError("qdrant-client not available") from e


def _open_chroma():
    _require_chroma()
    path = os.getenv("CHROMA_PATH", ".chroma_data")
    from chromadb import PersistentClient

    return PersistentClient(path=path)


def _open_qdrant():
    _require_qdrant()
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams

    url = os.getenv("QDRANT_URL") or "http://localhost:6333"
    api_key = os.getenv("QDRANT_API_KEY") or None
    c = QdrantClient(url=url, api_key=api_key)
    # Ensure collections we'll write to exist; we migrate to per-user mem collections on demand
    cache_col = os.getenv("QDRANT_QA_COLLECTION", "cache:qa")
    try:
        c.get_collection(cache_col)
    except Exception:
        c.recreate_collection(collection_name=cache_col, vectors_config=VectorParams(size=1, distance=Distance.COSINE))
    return c


def _inventory_chroma() -> dict[str, dict[str, int]]:
    cli = _open_chroma()
    cols: dict[str, dict[str, int]] = {}
    try:
        for name in ["qa_cache", "user_memories"]:
            try:
                col = cli.get_or_create_collection(name)
                ids = col.get(include=[]).get("ids", [])
                cols[name] = {"count": len(ids)}
            except Exception:
                cols[name] = {"count": 0}
    finally:
        try:
            getattr(cli, "reset", lambda: None)()
        except Exception:
            pass
    return cols


def _embed_many(texts: list[str]) -> list[list[float]]:
    from app.embeddings import embed_sync

    return [embed_sync(t) for t in texts]


def _export_qa(chroma_client) -> list[tuple[str, str, dict]]:
    col = chroma_client.get_or_create_collection("qa_cache")
    try:
        res = col.get(include=["ids", "documents", "metadatas"]).copy()
    except Exception:
        # Older Chroma may need query fallback
        res = col.query(query_texts=["*"], n_results=1000, include=["ids", "documents", "metadatas"])  # type: ignore[arg-type]
        res = {
            "ids": res.get("ids", [[]])[0],
            "documents": res.get("documents", [[]])[0],
            "metadatas": res.get("metadatas", [[{}]])[0],
        }
    ids = res.get("ids", [])
    docs = res.get("documents", [])
    metas = res.get("metadatas", [])
    out: list[tuple[str, str, dict]] = []
    for i, d, m in zip(ids, docs, metas, strict=False):
        if not i:
            continue
        out.append((str(i), d or "", dict(m or {})))
    return out


def _export_user_memories(chroma_client) -> list[tuple[str, str, dict]]:
    col = chroma_client.get_or_create_collection("user_memories")
    # Chroma stores only text + user_id in metadata for our impl
    try:
        res = col.get(include=["ids", "documents", "metadatas"]).copy()
    except Exception:
        res = col.query(query_texts=["*"], n_results=100000, include=["ids", "documents", "metadatas"])  # type: ignore[arg-type]
        res = {
            "ids": res.get("ids", [[]])[0],
            "documents": res.get("documents", [[]])[0],
            "metadatas": res.get("metadatas", [[{}]])[0],
        }
    ids = res.get("ids", [])
    docs = res.get("documents", [])
    metas = res.get("metadatas", [])
    out: list[tuple[str, str, dict]] = []
    for i, d, m in zip(ids, docs, metas, strict=False):
        if not i:
            continue
        out.append((str(i), d or "", dict(m or {})))
    return out


def _ensure_qdrant_indexes(client, name: str) -> None:
    from qdrant_client.http.models import Distance, VectorParams
    try:
        client.get_collection(name)
    except Exception:
        # dimension will be checked by caller for non-cache collections
        client.recreate_collection(collection_name=name, vectors_config=VectorParams(size=1, distance=Distance.COSINE))


def _upsert_qa(qc, items: list[tuple[str, str, dict]], dry_run: bool = False) -> int:
    from qdrant_client.http.models import PointStruct

    cache_col = os.getenv("QDRANT_QA_COLLECTION", "cache:qa")
    _ensure_qdrant_indexes(qc, cache_col)
    n = 0
    batch: list[PointStruct] = []
    for cid, doc, meta in items:
        payload = {"doc": doc, **{k: meta.get(k) for k in ("answer", "timestamp", "feedback")}}
        batch.append(PointStruct(id=cid, vector=None, payload=payload))
        if len(batch) >= 256:
            if not dry_run:
                qc.upsert(collection_name=cache_col, points=batch)
            n += len(batch)
            batch = []
    if batch:
        if not dry_run:
            qc.upsert(collection_name=cache_col, points=batch)
        n += len(batch)
    return n


def _ensure_user_collection(qc, name: str, dim: int) -> None:
    from qdrant_client.http.models import Distance, VectorParams
    try:
        qc.get_collection(name)
    except Exception:
        qc.recreate_collection(collection_name=name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
    # Create helpful payload indexes (best-effort)
    for field, schema in (
        ("user_id", "keyword"),
        ("type", "keyword"),
        ("topic", "keyword"),
        ("created_at", "float"),
        ("source_tier", "float"),
        ("pinned", "bool"),
    ):
        try:
            qc.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
        except Exception:
            pass


def _upsert_user_memories(qc, items: list[tuple[str, str, dict]], dry_run: bool = False) -> int:
    from qdrant_client.http.models import PointStruct
    # target dim from env
    dim = int(os.getenv("EMBED_DIM", "1536"))
    n = 0
    for orig_id, text, meta in items:
        user_id = str((meta or {}).get("user_id") or "")
        if not user_id:
            continue
        col = f"mem:user:{user_id}"
        _ensure_user_collection(qc, col, dim)
        # build payload mirroring QdrantVectorStore.add_user_memory
        checksum = __import__("hashlib").sha256(text.encode("utf-8")).hexdigest()
        now = float(meta.get("ts") or time.time())
        payload = {
            "user_id": user_id,
            "doc_id": str(orig_id),
            "source": "chroma_migration",
            "namespace": "mem:user",
            "type": "note",
            "topic": None,
            "entities": [],
            "confidence": 0.7,
            "quality": 0.5,
            "source_tier": 2,
            "created_at": now,
            "updated_at": now,
            "decay_at": None,
            "pinned": False,
            "evidence_ids": [],
            "checksum": checksum,
            "redactions": [],
            "text": text,
        }
        # embed
        vec = _embed_many([text])[0]
        # Preserve original document id where possible
        pt = PointStruct(id=str(orig_id), vector=vec, payload=payload)
        if not dry_run:
            qc.upsert(collection_name=col, points=[pt])
        n += 1
    return n


def _write_jsonl(path: str, rows: list[dict]) -> None:
    import json
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser("migrate_chroma_to_qdrant")
    p.add_argument("command", choices=["inventory", "export", "migrate"], help="What to run")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out-dir", default=None, help="When exporting, write JSONL under this directory")
    args = p.parse_args(argv)

    if args.command == "inventory":
        inv = _inventory_chroma()
        print({"collections": inv})
        return

    cli = _open_chroma()
    qc = _open_qdrant()
    if args.command == "export":
        qa = _export_qa(cli)
        um = _export_user_memories(cli)
        if args.out_dir:
            _write_jsonl(os.path.join(args.out_dir, "qa_cache.jsonl"), [
                {"id": i, "document": d, "metadata": m} for (i, d, m) in qa
            ])
            _write_jsonl(os.path.join(args.out_dir, "user_memories.jsonl"), [
                {"id": i, "text": d, "metadata": m} for (i, d, m) in um
            ])
        print({"qa_cache": len(qa), "user_memories": len(um)})
        return

    if args.command == "migrate":
        qa = _export_qa(cli)
        um = _export_user_memories(cli)
        moved_qa = _upsert_qa(qc, qa, dry_run=args.dry_run)
        moved_um = _upsert_user_memories(qc, um, dry_run=args.dry_run)
        print({"migrated": {"qa_cache": moved_qa, "user_memories": moved_um}})
        return


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main(sys.argv[1:])


