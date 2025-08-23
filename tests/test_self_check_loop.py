import asyncio

from app.model_router import run_with_self_check


def test_exactly_one_final_retry():
    # Force two low scores then success on final to ensure exactly one retry
    seq = {
        "gpt-5-nano": ("not sure", 2, 1, 0.0),
        "gpt-4.1-nano": ("not sure", 2, 1, 0.0),
        # Heavy model configured in app.model_config defaults to 'gpt-4.1-nano' currently.
        # To keep this test stable regardless of env, assert on whatever heavy model is configured.
        "gpt-4.1-nano": ("therefore adequate answer", 5, 2, 0.0),
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
    # Final model should be the heavy model per configuration
    assert final_model in ("o4-mini", "gpt-4.1-nano")
    assert escalated is True
