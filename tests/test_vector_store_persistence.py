from app.memory.memory_store import MemoryVectorStore


def test_vector_store_ttl_eviction(monkeypatch):
    vs = MemoryVectorStore()
    # shorten TTL for test
    vs._cache._ttl_seconds = 0.001  # type: ignore[attr-defined]
    vs.cache_answer("id1", "hello", "world")
    # force eviction by calling get_items after sleeping
    import time

    time.sleep(0.01)
    # trigger eviction
    _ = vs.qa_cache.get_items()
    # lookup should miss
    assert vs.lookup_cached_answer("hello") is None


def test_vector_store_user_namespace():
    vs = MemoryVectorStore()
    uid_a, uid_b = "A", "B"
    vs.add_user_memory(uid_a, "alpha")
    vs.add_user_memory(uid_b, "beta")
    res_a = vs.query_user_memories(uid_a, "alpha", k=5)
    res_b = vs.query_user_memories(uid_b, "beta", k=5)
    assert any("alpha" in x for x in res_a)
    assert any("beta" in x for x in res_b)


