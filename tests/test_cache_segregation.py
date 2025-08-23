from app.memory.vector_store import cache_answer, lookup_cached_answer
from app.model_router import compose_cache_id


def test_cache_segregation_by_model():
    prompt = "What is the capital of France?"
    cid_nano = compose_cache_id("gpt-5-nano", prompt, [])
    cid_41 = compose_cache_id("gpt-4.1-nano", prompt, [])

    cache_answer(prompt=cid_nano, answer="Paris (fast)")
    assert lookup_cached_answer(cid_nano) == "Paris (fast)"
    assert lookup_cached_answer(cid_41) is None  # no cross-contamination


def test_cache_segregation_different_models_same_prompt():
    prompt = "Who won the match?"
    cid_a = compose_cache_id("gpt-5-nano", prompt, [])
    cid_b = compose_cache_id("gpt-4.1-nano", prompt, [])
    cache_answer(prompt=cid_a, answer="Team A")
    cache_answer(prompt=cid_b, answer="Team B")
    assert lookup_cached_answer(cid_a) == "Team A"
    assert lookup_cached_answer(cid_b) == "Team B"


