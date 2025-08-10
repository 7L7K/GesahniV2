import re
from app.prompt_builder import PromptBuilder


def _anonize(text: str) -> str:
    # Remove ISO timestamps and trailing spaces
    text = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:[0-9.]+\+00:00", "<ts>", text)
    return text.strip()


def test_prompt_snapshot_stable(monkeypatch):
    # Stable memories and summary
    import app.prompt_builder as pb

    monkeypatch.setattr(pb.memgpt, "summarize_session", lambda *a, **k: "summary")
    monkeypatch.setattr(pb, "safe_query_user_memories", lambda *a, **k: ["m1", "m2"])

    prompt, _ = PromptBuilder.build("hello", session_id="s", user_id="u", debug=True, debug_info="DBG")
    snap = _anonize(prompt)
    assert "summary" in snap and "m1" in snap and "hello" in snap and "DBG" in snap


