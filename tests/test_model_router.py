import os
import asyncio

from app.model_router import (
    route_text,
    run_with_self_check,
    compose_cache_id,
    triage_scene_risk,
)


class Dummy:
    pass


async def fake_ask(prompt, model, system, **kwargs):
    # Craft deterministic answers: short/weak for nano; longer for escalations
    if model == "gpt-5-nano":
        return "not sure", 10, 2, 0.0
    if model == "gpt-4.1-nano":
        return "because this is adequate answer with details", 20, 5, 0.0
    if model == "o4-mini":
        return "therefore final safety-level explanation sufficient", 30, 7, 0.0
    return "ok", 1, 1, 0.0


def test_compose_cache_id_stable():
    cid1 = compose_cache_id("gpt-5-nano", "Hello World", ["doc A", "doc B"])
    cid2 = compose_cache_id("gpt-5-nano", "Hello  World ", ["doc B", "doc A"])  # reordered
    assert cid1 == cid2
    assert cid1.startswith("v1|gpt-5-nano|")


def test_route_text_defaults_to_nano():
    d = route_text(user_prompt="hi", prompt_tokens=3, retrieved_docs=[], intent="chat")
    assert d.model == "gpt-5-nano"
    assert d.reason == "default"


def test_route_text_long_prompt_escalates():
    long_prompt = "a" * 300
    d = route_text(user_prompt=long_prompt, prompt_tokens=300, retrieved_docs=[])
    assert d.model == "gpt-4.1-nano"
    assert d.reason == "long-prompt"


def test_run_with_self_check_escalates_then_passes():
    import asyncio

    text, model, reason, score, pt, ct, cost, escalated = asyncio.run(
        run_with_self_check(
            ask_func=fake_ask,
            model="gpt-5-nano",
            user_prompt="hello",
            system_prompt=None,
            retrieved_docs=[],
            threshold=0.60,
            max_retries=1,
        )
    )
    assert model in {"gpt-4.1-nano", "o4-mini"}
    assert escalated is True
    assert score >= 0.0


def test_vision_triage():
    assert triage_scene_risk("a cat") == "low"
    assert triage_scene_risk("warning sign on damaged road") in {"medium", "high"}
    assert triage_scene_risk("blood and injury") == "high"


