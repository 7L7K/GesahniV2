import asyncio

from app.model_router import run_with_self_check


async def ask_always_weak(prompt, model, system, **kwargs):
    return "not sure", 10, 1, 0.0


async def ask_then_strong(prompt, model, system, **kwargs):
    if model == "gpt-5-nano":
        return "not sure", 10, 1, 0.0
    return "therefore adequate detailed answer", 20, 2, 0.0


def test_escalates_after_two_failures():

    text, model, reason, score, pt, ct, cost, escalated = asyncio.run(
        run_with_self_check(
            ask_func=ask_then_strong,
            model="gpt-5-nano",
            user_prompt="hello",
            system_prompt=None,
            retrieved_docs=[],
            threshold=0.60,
            max_retries=1,
        )
    )
    assert escalated is True
    assert model in {"gpt-4.1-nano", "o4-mini"}


def test_final_retry_o4_mini():

    text, model, reason, score, pt, ct, cost, escalated = asyncio.run(
        run_with_self_check(
            ask_func=ask_always_weak,
            model="gpt-5-nano",
            user_prompt="hello",
            system_prompt=None,
            retrieved_docs=[],
            threshold=0.95,
            max_retries=1,
        )
    )
    # with high threshold and one retry, it should escalate at least once
    assert escalated is True
    assert model in {"gpt-4.1-nano", "o4-mini"}
