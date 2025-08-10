from app.memory import vector_store


def test_safe_query_user_memories_coerces_k(monkeypatch):
    captured: dict[str, int | None] = {}

    def fake_query(uid: str, prompt: str, *, k=None, filters=None):
        captured["k"] = k
        return []

    monkeypatch.setattr(vector_store, "query_user_memories", fake_query)

    vector_store.safe_query_user_memories("u", "p", k="3")
    assert captured["k"] == 3

    vector_store.safe_query_user_memories("u", "p", k="bad")
    assert captured["k"] is None
