from app import prompt_builder
from app.prompt_builder import PromptBuilder, MAX_PROMPT_TOKENS


def test_prompt_builder_respects_token_limit(monkeypatch):
    big = "token " * 12000
    monkeypatch.setattr(prompt_builder.memgpt, "summarize_session", lambda sid: big)
    monkeypatch.setattr(prompt_builder, "query_user_memories", lambda uid, q, n_results=5: [big, big])

    prompt, tokens = PromptBuilder.build("hi", session_id="s", user_id="u")
    assert tokens <= MAX_PROMPT_TOKENS
