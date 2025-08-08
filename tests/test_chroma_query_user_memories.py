from app.memory import chroma_store


class _DummyCollection:
    def query(self, *, query_texts, where, n_results, include):
        return {
            "documents": [["good", "bad", "another"]],
            "distances": [[0.2, 0.6, 0.2]],
            "metadatas": [[{"ts": 1}, {"ts": 2}, {"ts": 3}]],
        }


def test_query_user_memories_recomputes_and_sorts(monkeypatch):
    store = object.__new__(chroma_store.ChromaVectorStore)
    store._user_memories = _DummyCollection()
    store._dist_cutoff = 0.0
    monkeypatch.setattr(chroma_store, "_get_sim_threshold", lambda: 0.5)

    res = store.query_user_memories("u", "prompt", k=5)

    assert store._dist_cutoff == 0.5
    assert res == ["another", "good"]
