def test_chroma_length_metric_does_not_over_filter(monkeypatch):
    # Ensure length embedder is used
    monkeypatch.delenv("CHROMA_EMBEDDER", raising=False)
    from app.memory.chroma_store import ChromaVectorStore
    vs = ChromaVectorStore()
    # Seed two docs of different lengths for same user
    user = "u"
    vs.add_user_memory(user, "short")
    vs.add_user_memory(user, "a much longer memory text here")
    res = vs.query_user_memories(user, "short prompt", k=2)
    assert len(res) >= 1


