import os
import types
import pytest


def test_dual_read_fallbacks_to_chroma_when_primary_empty(monkeypatch, tmp_path):
    # Configure dual; make chroma available
    monkeypatch.setenv("VECTOR_STORE", "dual")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))

    # Stub qdrant vector store to return empty for reads
    import app.memory.vector_store.qdrant as qvs

    class _FakeQdrant(qvs.QdrantVectorStore):  # type: ignore
        def __init__(self):
            pass

        def query_user_memories(self, user_id: str, prompt: str, k: int = 5):
            return []

        def add_user_memory(self, user_id: str, memory: str) -> str:
            return "id"

        @property
        def qa_cache(self):
            class _C:
                def get_items(self, *a, **k):
                    return {"ids": []}

                def upsert(self, *a, **k):
                    pass

                def delete(self, *a, **k):
                    pass

                def update(self, *a, **k):
                    pass

            return _C()

    monkeypatch.setattr(qvs, "QdrantVectorStore", _FakeQdrant)

    # Build dual store and seed fallback (Chroma) with a memory
    from app.memory.vector_store.dual import DualReadVectorStore
    from app.memory.chroma_store import ChromaVectorStore

    fb = ChromaVectorStore()
    mid = fb.add_user_memory("u", "hello world")
    assert mid

    # Monkey-patch fallback inside DualReadVectorStore after construction
    dual = DualReadVectorStore()
    dual._fallback = fb  # type: ignore[attr-defined]

    res = dual.query_user_memories("u", "hello")
    assert res == ["hello world"]


