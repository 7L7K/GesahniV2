from app.model_router import compose_cache_id
from app.memory.vector_store import cache_answer, lookup_cached_answer


def test_cache_segregation_by_model():
    prompt = "What is the capital of France?"
    cid_nano = compose_cache_id("gpt-5-nano", prompt, [])
    cid_41 = compose_cache_id("gpt-4.1-nano", prompt, [])

    cache_answer(prompt=cid_nano, answer="Paris (fast)")
    assert lookup_cached_answer(cid_nano) == "Paris (fast)"
    assert lookup_cached_answer(cid_41) is None  # no cross-contamination


