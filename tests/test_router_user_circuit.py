import asyncio
import os

from fastapi import HTTPException


def test_per_user_llama_circuit(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["LLAMA_USER_CB_THRESHOLD"] = "1"
    from app import router as r
    # Directly lower threshold for this test since module constants are bound at import
    r._USER_CB_THRESHOLD = 1

    # Healthy global state
    monkeypatch.setattr(r.llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(r, "handle_command", lambda p: None)
    monkeypatch.setattr(r, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(r, "pick_model", lambda *a, **k: ("llama", "llama3"))
    monkeypatch.setattr(r, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(r.PromptBuilder, "build", staticmethod(lambda *a, **k: (a[0], 0)))

    # First call raises causing breaker increment
    async def _fail_llama(**kwargs):
        raise HTTPException(status_code=503, detail="down")

    monkeypatch.setattr(r, "_call_llama", _fail_llama)
    try:
        asyncio.run(r.route_prompt("hi", user_id="u1"))
    except HTTPException:
        pass

    # After failure, user breaker should steer to GPT path
    async def _ok_gpt(**kwargs):
        return "ok"

    monkeypatch.setattr(r, "_call_gpt", _ok_gpt)
    out = asyncio.run(r.route_prompt("hi", user_id="u1"))
    assert out == "ok"


