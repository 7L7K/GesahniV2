import time
from app.memory.memgpt import MemGPT
from app.memory import vector_store


def test_memgpt_dedup_and_maintenance(tmp_path):
    m = MemGPT(storage_path=tmp_path / "mem.json", ttl_seconds=1)
    m.store_interaction("hello", "world", session_id="s")
    m.store_interaction("hello", "world", session_id="s")
    assert len(m._data["s"]) == 1
    m._data["s"][0]["timestamp"] = time.time() - 2
    m.nightly_maintenance()
    assert m._data["s"][0]["prompt"] == "summary"


def test_vector_store_ttl_and_feedback():
    h = "hash123"
    vector_store.cache_answer(h, "answer")
    assert vector_store.lookup_cached_answer(h, ttl_seconds=100) == "answer"
    vector_store._qa_cache.update(ids=[h], metadatas=[{"timestamp": time.time() - 200}])
    assert vector_store.lookup_cached_answer(h, ttl_seconds=100) is None
    vector_store.cache_answer(h, "answer2")
    vector_store.record_feedback(h, "down")
    assert vector_store.lookup_cached_answer(h) is None
