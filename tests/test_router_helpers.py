import asyncio

from app import router
from app.telemetry import LogRecord


def make_record(prompt: str = "hi"):
    return LogRecord(req_id="1", prompt=prompt, session_id="s", user_id="u")


def test_call_gpt(monkeypatch):
    async def fake_ask_gpt(prompt, model, system, **kwargs):
        return "gpt answer", 10, 2, 0.01

    calls = {}

    async def fake_append(prompt, engine, resp):
        calls["history"] = (prompt, engine, resp)

    async def fake_record(engine, fallback=False, source="gpt"):
        calls["record"] = (engine, fallback)

    monkeypatch.setattr(router, "ask_gpt", fake_ask_gpt)
    monkeypatch.setattr(router, "append_history", fake_append)
    monkeypatch.setattr(router, "record", fake_record)
    monkeypatch.setattr(
        router.memgpt,
        "store_interaction",
        lambda *a, **k: calls.setdefault("mem", True),
    )
    monkeypatch.setattr(
        router, "add_user_memory", lambda *a, **k: calls.setdefault("mem_add", True)
    )
    monkeypatch.setattr(
        router, "cache_answer", lambda *a, **k: calls.setdefault("cache", True)
    )

    rec = make_record("hello")
    result = asyncio.run(
        router._call_gpt(
            built_prompt="built",
            model="gpt-4",
            rec=rec,
            norm_prompt="hello",
            session_id="s",
            user_id="u",
            ptoks=5,
            prompt="hello",
        )
    )

    assert result == "gpt answer"
    assert rec.engine_used == "gpt"
    assert rec.model_name == "gpt-4"
    assert rec.prompt_tokens == 10
    assert rec.completion_tokens == 2
    assert calls["history"] == ("hello", "gpt", "gpt answer")
    assert calls["record"] == ("gpt", False)
    assert calls.get("cache") is True


def test_call_llama_success(monkeypatch):
    async def fake_llama(prompt, model):
        return "llama answer"

    calls = {}

    async def fake_append(prompt, engine, resp):
        calls["history"] = (prompt, engine, resp)

    async def fake_record(engine, fallback=False, source="gpt"):
        calls["record"] = (engine, fallback)

    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "append_history", fake_append)
    monkeypatch.setattr(router, "record", fake_record)
    monkeypatch.setattr(
        router.memgpt,
        "store_interaction",
        lambda *a, **k: calls.setdefault("mem", True),
    )
    monkeypatch.setattr(
        router, "add_user_memory", lambda *a, **k: calls.setdefault("mem_add", True)
    )
    monkeypatch.setattr(
        router, "cache_answer", lambda *a, **k: calls.setdefault("cache", True)
    )

    rec = make_record("hi")
    result = asyncio.run(
        router._call_llama(
            built_prompt="built",
            model="llama3",
            rec=rec,
            norm_prompt="hi",
            session_id="s",
            user_id="u",
            ptoks=7,
            prompt="hi",
        )
    )

    assert result == "llama answer"
    assert rec.engine_used == "llama"
    assert rec.model_name == "llama3"
    assert rec.prompt_tokens == 7
    assert calls["history"] == ("hi", "llama", "llama answer")
    assert calls["record"] == ("llama", False)


def test_call_llama_fallback(monkeypatch):
    async def fake_llama(prompt, model):
        return {"error": "timeout", "llm_used": model}

    async def fake_gpt(prompt, model, system, **kwargs):
        return "gpt fallback", 0, 0, 0.0

    calls = {"records": []}

    async def fake_append(prompt, engine, resp):
        calls.setdefault("history", []).append((engine, resp))

    async def fake_record(engine, fallback=False, source="gpt"):
        calls["records"].append((engine, fallback))

    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    monkeypatch.setattr(router, "append_history", fake_append)
    monkeypatch.setattr(router, "record", fake_record)
    monkeypatch.setattr(router.memgpt, "store_interaction", lambda *a, **k: None)
    monkeypatch.setattr(router, "add_user_memory", lambda *a, **k: None)
    monkeypatch.setattr(router, "cache_answer", lambda *a, **k: None)

    rec = make_record("fallback")
    result = asyncio.run(
        router._call_llama(
            built_prompt="built",
            model="llama3",
            rec=rec,
            norm_prompt="fallback",
            session_id="s",
            user_id="u",
            ptoks=5,
            prompt="fallback",
        )
    )

    assert result == "gpt fallback"
    assert ("gpt", True) in calls["records"]
    assert rec.engine_used == "gpt"
