import asyncio

from app.model_router import run_with_self_check


def test_exactly_one_final_retry():
    # Force two low scores then success on final to ensure exactly one retry
    seq = {
        "gpt-5-nano": ("not sure", 2, 1, 0.0),
        "gpt-4.1-nano": ("not sure", 2, 1, 0.0),
        "o4-mini": ("therefore adequate answer", 5, 2, 0.0),
    }

    async def ask_seq(prompt, model, system, **kwargs):
        return seq[model]

    text, final_model, reason, score, pt, ct, cost, escalated = asyncio.run(
        run_with_self_check(
            ask_func=ask_seq,
            model="gpt-5-nano",
            user_prompt="force escalate",
            system_prompt=None,
            retrieved_docs=[],
            threshold=0.9,
            max_retries=1,
        )
    )
    assert final_model == "o4-mini"
    assert escalated is True

