import asyncio

from app.model_router import run_with_self_check


async def _ask_low(prompt, model, system, **kwargs):
    return "not sure", 3, 1, 0.0


def test_quota_breach_disables_escalation(monkeypatch):
    monkeypatch.setenv("BUDGET_QUOTA_BREACHED", "1")
    text, model, reason, score, pt, ct, cost, escalated = asyncio.run(
        run_with_self_check(
            ask_func=_ask_low,
            model="gpt-5-nano",
            user_prompt="x",
            system_prompt="You are in Granny Mode.",
            retrieved_docs=[],
            threshold=0.95,
            max_retries=1,
        )
    )
    assert model == "gpt-5-nano"
    assert escalated is False


def test_reply_len_target_reduced_under_budget(monkeypatch):
    monkeypatch.setenv("BUDGET_QUOTA_BREACHED", "1")

    async def ask_wordy(prompt, model, system, **kwargs):
        # Produce moderately long answer; heuristic target should clamp lower
        return ("because " + ("ok " * 50)).strip(), 50, 20, 0.0

    text, model, reason, score, pt, ct, cost, escalated = asyncio.run(
        run_with_self_check(
            ask_func=ask_wordy,
            model="gpt-5-nano",
            user_prompt="long form",
            system_prompt="You are in Granny Mode.",
            retrieved_docs=[],
            threshold=0.1,
            max_retries=1,
        )
    )
    # Should not escalate and score should be computed against reduced target;
    # not asserting exact score, only that no escalation occurred
    assert escalated is False

