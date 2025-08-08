import pytest
import app.memory.vector_store as vs


@pytest.mark.parametrize("store_cls", [vs.MemoryVectorStore, vs.ChromaVectorStore])
def test_cache_roundtrip(monkeypatch, tmp_path, store_cls):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    monkeypatch.setattr(vs, "embed_sync", lambda text: [float(len(text))])
    store = store_cls()
    try:
        cache_id = vs._normalized_hash("hello")
        store.cache_answer(cache_id, "hello", "world")
        assert store.lookup_cached_answer("hello") == "world"
        store.record_feedback("hello", "down")
        assert store.lookup_cached_answer("hello") is None
    finally:
        store.close()
