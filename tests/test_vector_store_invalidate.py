from app.memory import vector_store


def test_invalidate_cache_clears_entry():
    # Ensure cache is empty
    vector_store.qa_cache.delete(ids=vector_store._qa_cache.get()["ids"])

    prompt = "Fancy “quotes”—and dashes"
    answer = "cached"
    cache_id = vector_store._normalized_hash(prompt)
    vector_store.cache_answer(cache_id, prompt, answer)
    assert vector_store.lookup_cached_answer(prompt) == answer

    # Invalidate using a variant that normalizes to the same text
    vector_store.invalidate_cache('Fancy "quotes"-and dashes')
    assert vector_store.lookup_cached_answer(prompt) is None
