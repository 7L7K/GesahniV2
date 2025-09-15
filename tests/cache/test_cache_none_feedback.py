import pytest

from app.memory.vector_store import ChromaVectorStore


@pytest.fixture
def store():
    s = ChromaVectorStore()
    yield s
    s.close()


def test_cache_allows_none_feedback(monkeypatch, store):
    # Wrap the underlying upsert to ensure metadata values are cleaned of None
    original_upsert = store._cache.upsert

    def wrapped_upsert(*args, **kwargs):
        meta = kwargs["metadatas"][0]
        assert None not in meta.values()
        return original_upsert(*args, **kwargs)

    monkeypatch.setattr(store._cache, "upsert", wrapped_upsert)

    store.cache_answer("1", "hello", "world")
    assert store.lookup_cached_answer("hello") == "world"
