import pytest
from app.memory.chroma_store import ChromaVectorStore
from app.memory.memory_store import MemoryVectorStore


@pytest.mark.parametrize("store_cls", [MemoryVectorStore, ChromaVectorStore])
def test_unrelated_query_returns_empty(monkeypatch, tmp_path, store_cls):
    monkeypatch.setenv("SIM_THRESHOLD", "0.99")
    if store_cls is ChromaVectorStore:
        pytest.importorskip("chromadb")
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    store = store_cls()
    try:
        store.add_user_memory("u", "hello world")
        assert store.query_user_memories("u", "totally unrelated prompt") == []
    finally:
        store.close()
