import os
import asyncio

from app.model_router import (
    route_text,
    run_with_self_check,
    compose_cache_id,
    triage_scene_risk,
    route_vision,
)
from app.model_config import (
    GPT_BASELINE_MODEL,
    GPT_MID_MODEL,
    GPT_HEAVY_MODEL,
)


class Dummy:
    pass


async def fake_ask(prompt, model, system, **kwargs):
    # Craft deterministic answers: short/weak for nano; longer for escalations
    if model == "gpt-5-nano":
        return "not sure", 10, 2, 0.0
    if model == "gpt-4.1-nano":
        return "because this is adequate answer with details", 20, 5, 0.0
    if model == GPT_HEAVY_MODEL:
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
    assert model in {"gpt-4.1-nano", GPT_HEAVY_MODEL}
    assert escalated is True
    assert score >= 0.0


def test_vision_triage():
    assert triage_scene_risk("a cat") == "low"
    assert triage_scene_risk("warning sign on damaged road") in {"medium", "high"}
    assert triage_scene_risk("blood and injury") == "high"


def test_route_text_attachments_branch():
    d = route_text(user_prompt="see image", prompt_tokens=3, retrieved_docs=[], attachments_count=1)
    assert d.model == "gpt-4.1-nano"
    assert d.reason == "attachments"


def test_route_text_ops_branches():
    # simple ops → nano
    d_simple = route_text(user_prompt="rename files", intent="ops", ops_files_count=1)
    assert d_simple.model == "gpt-5-nano"
    assert d_simple.reason == "ops-simple"
    # complex ops → 4.1-nano
    d_complex = route_text(user_prompt="refactor repo", intent="ops", ops_files_count=5)
    assert d_complex.model == "gpt-4.1-nano"
    assert d_complex.reason == "ops-complex"


def test_route_text_keyword_escalates():
    d = route_text(user_prompt="please summarize this", intent="chat")
    assert d.model == "gpt-4.1-nano"
    assert d.reason == "keyword"


def test_route_text_heavy_intent_escalates():
    d = route_text(user_prompt="hi", intent="analysis")
    assert d.model == "gpt-4.1-nano"
    assert d.reason == "heavy-intent"


def test_route_vision_cap(monkeypatch):
    # Force a tiny cap via env; verify local-only after cap
    monkeypatch.setenv("VISION_MAX_IMAGES_PER_DAY", "1")
    # Reset vision counters to avoid cross-test flakiness
    import app.model_router as mr
    mr._VISION_DAY = None
    mr._VISION_COUNT = 0

    calls = []

    async def ask_stub(prompt, model, system, **kwargs):
        calls.append(model)
        return "ok", 0, 0, 0.0

    # first call allowed → remote mini
    model, reason = asyncio.run(route_vision(ask_func=ask_stub, images=[b"img"], text_hint="person", allow_test=True))
    assert model in {GPT_BASELINE_MODEL, GPT_MID_MODEL}
    # second call blocked → local
    model2, reason2 = asyncio.run(route_vision(ask_func=ask_stub, images=[b"img"], text_hint="person", allow_test=True))
    assert model2 == "local"
    assert reason2 == "vision-local-cap"


def test_budget_caps_disable_escalations(monkeypatch):
    monkeypatch.setenv("BUDGET_QUOTA_BREACHED", "1")

    async def ask_low(prompt, model, system, **kwargs):
        return "not sure", 2, 1, 0.0

    # With quota breached, there should be no escalation and exactly one attempt
    text, model, reason, score, pt, ct, cost, escalated = asyncio.run(
        run_with_self_check(
            ask_func=ask_low,
            model="gpt-5-nano",
            user_prompt="short",
            system_prompt="You are in Granny Mode.",
            retrieved_docs=[],
            threshold=0.99,
            max_retries=1,
        )
    )
    assert model == "gpt-5-nano"
    assert escalated is False


def test_self_check_single_retry_to_mid_tier():
    # With MAX_ESCALATIONS=1, only one retry to mid-tier should happen
    seq = {
        "gpt-5-nano": ("not sure", 5, 1, 0.0),
        "gpt-4.1-nano": ("because adequate", 10, 2, 0.0),
    }

    async def ask_seq(prompt, model, system, **kwargs):
        return seq[model]

    text, model, reason, score, pt, ct, cost, escalated = asyncio.run(
        run_with_self_check(
            ask_func=ask_seq,
            model="gpt-5-nano",
            user_prompt="force escalate",
            system_prompt=None,
            retrieved_docs=[],
            threshold=0.6,
            max_retries=1,
        )
    )
    assert model == "gpt-4.1-nano"
    assert escalated is True


