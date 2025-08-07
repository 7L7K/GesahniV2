import types
import pytest
from app.memory.vector_store import ChromaVectorStore


@pytest.fixture
def store():
    s = ChromaVectorStore()
    yield s
    s.close()


def test_memory_env_reload(monkeypatch, store):
    fake_collection = types.SimpleNamespace(
        query=lambda query_texts, n_results, include: {
            "documents": [["A", "B"]],
            "distances": [[0.1, 0.2]],
            "metadatas": [[{"ts": 1}, {"ts": 2}]],
        }
    )
    monkeypatch.setattr(store, "_user_memories", fake_collection)
    monkeypatch.setenv("SIM_THRESHOLD", "0")
    monkeypatch.setenv("MEM_TOP_K", "1")
    assert store.query_user_memories("u", "x") == ["A"]
    monkeypatch.setenv("MEM_TOP_K", "2")
    assert store.query_user_memories("u", "x") == ["A", "B"]
    monkeypatch.setenv("SIM_THRESHOLD", "0.95")
    assert store.query_user_memories("u", "x") == []
