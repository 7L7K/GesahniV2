import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _setup_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://x")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "token")
    monkeypatch.setenv("DEBUG_MODEL_ROUTING", "1")


def _common_patches(monkeypatch, router):
    async def _handle(_):
        return None

    monkeypatch.setattr(router, "handle_command", _handle)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(
        router.PromptBuilder, "build", staticmethod(lambda prompt, **kw: ("p", 0))
    )


async def _fail(*args, **kwargs):  # pragma: no cover - should not be called
    raise AssertionError("external call executed")


def test_dry_run_llama_path(monkeypatch, caplog):
    _setup_env(monkeypatch)
    from app import router, llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    _common_patches(monkeypatch, router)
    monkeypatch.setattr(router, "ask_llama", _fail)
    monkeypatch.setattr(router, "ask_gpt", _fail)

    with caplog.at_level(logging.INFO):
        result = asyncio.run(router.route_prompt("hi", user_id="u"))

    assert result == "[dry-run] would call llama llama3"
    assert "would call llama llama3" in caplog.text


def test_dry_run_gpt_fallback(monkeypatch, caplog):
    _setup_env(monkeypatch)
    from app import router, llama_integration

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", False)
    _common_patches(monkeypatch, router)
    monkeypatch.setattr(router, "ask_llama", _fail)
    monkeypatch.setattr(router, "ask_gpt", _fail)

    with caplog.at_level(logging.INFO):
        result = asyncio.run(router.route_prompt("hi", user_id="u"))

    assert result == "[dry-run] would call gpt gpt-4o"
    assert "would call gpt gpt-4o" in caplog.text
