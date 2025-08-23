import asyncio
import builtins
import os
import sys
import types
from typing import Any

import httpx
import pytest  # noqa: E402
from fastapi import HTTPException

# Setup sys.modules mocks for import isolation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.modules.setdefault(
    "sentence_transformers",
    types.SimpleNamespace(SentenceTransformer=object, util=None),
)
sys.modules.setdefault("chromadb", types.SimpleNamespace(PersistentClient=object))
sys.modules.setdefault("aiosqlite", types.SimpleNamespace(connect=lambda *a, **k: None))


# --- Metadata Cleaner ---
def clean_metadata(meta):
    return {k: (v if v is not None else "") for k, v in meta.items()} if meta else {}


# --- Mock Embeddings/OpenAI/AsyncOpenAI ---
class _Emb:
    def create(self, *a, **k):
        return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.0])])


class _OpenAI:
    def __init__(self, *a, **k):
        self.embeddings = _Emb()


class _ChatCompletionStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _ChatCompletions:
    async def create(self, *a, **k):
        if k.get("stream"):
            return _ChatCompletionStream()
        return types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(content=""),
                    delta=None,
                    finish_reason="stop",
                )
            ],
            usage=types.SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )


class _AsyncOpenAI:
    def __init__(self, *a, **k):
        self.chat = types.SimpleNamespace(completions=_ChatCompletions())
        self.embeddings = _Emb()

    async def close(self):
        pass


class _OpenAIError(Exception):
    pass


builtins.AsyncOpenAI = _AsyncOpenAI
sys.modules["openai"] = types.SimpleNamespace(
    OpenAI=_OpenAI, AsyncOpenAI=_AsyncOpenAI, OpenAIError=_OpenAIError
)


# --- Patch MemGPT & VectorStore Internals Globally ---
@pytest.fixture(autouse=True)
def patch_memgpt_and_vector(monkeypatch):
    from app import router
    from app.memory import vector_store

    # Patch MemGPT and any memory routines to pure no-op for tests
    monkeypatch.setattr(
        router, "memgpt", types.SimpleNamespace(store_interaction=lambda *a, **k: None)
    )
    monkeypatch.setattr(router, "add_user_memory", lambda *a, **k: None)
    monkeypatch.setattr(
        router, "cache_answer", lambda prompt, answer, cache_id=None: None
    )
    # Patch all vector store clearing for compatibility
    if hasattr(vector_store, "clear_cache"):
        monkeypatch.setattr(vector_store, "clear_cache", lambda: None)
    elif hasattr(vector_store, "_cache"):
        monkeypatch.setattr(vector_store._cache, "delete", lambda **kwargs: None)


# --- TESTS ---
def test_router_fallback_metrics_updated(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import analytics, llama_integration, router

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

    async def fake_llama(prompt, model=None):
        return {"error": "timeout", "llm_used": "llama3"}

    async def fake_gpt(prompt, model=None, system=None, **kwargs):
        return "ok", 0, 0, 0.0

    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    analytics._metrics = {
        "total": 0,
        "llama": 0,
        "gpt": 0,
        "fallback": 0,
        "session_count": 0,
        "transcribe_ms": 0,
        "transcribe_count": 0,
        "transcribe_errors": 0,
    }

    result = asyncio.run(router.route_prompt("hello world", user_id="u"))
    assert result == "ok"
    m = analytics.get_metrics()
    assert m["total"] == 1
    assert m["gpt"] == 1
    assert m["fallback"] == 1


def test_gpt_override(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import llama_integration, router

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

    async def fake_gpt(prompt, model=None, system=None, **kwargs):
        return model, 0, 0, 0.0

    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    monkeypatch.setattr(router, "ALLOWED_GPT_MODELS", {"gpt-4"})
    result = asyncio.run(router.route_prompt("hello world", "gpt-4", user_id="u"))
    assert result == "gpt-4"


def test_gpt_override_invalid(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router

    monkeypatch.setattr(router, "ALLOWED_GPT_MODELS", {"gpt-4"})
    with pytest.raises(HTTPException):
        asyncio.run(router.route_prompt("hello world", "gpt-3", user_id="u"))


def test_gpt_override_http_error_falls_back(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import llama_integration, router

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

    async def fake_gpt(*a, **k):
        raise httpx.HTTPError("boom")

    async def fake_llama(**kwargs):
        return "llama-ok"

    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    monkeypatch.setattr(router, "_call_llama", fake_llama)
    monkeypatch.setattr(router, "ALLOWED_GPT_MODELS", {"gpt-4"})

    result = asyncio.run(router.route_prompt("hi", "gpt-4", user_id="u"))
    assert result == "llama-ok"


def test_gpt_override_runtime_error_detail(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import llama_integration, router

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", False)

    async def fake_gpt(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    monkeypatch.setattr(router, "ALLOWED_GPT_MODELS", {"gpt-4"})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(router.route_prompt("hi", "gpt-4", user_id="u"))
    assert exc.value.status_code == 503
    assert "kaboom" in exc.value.detail


def test_complexity_checks(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import llama_integration, router

    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

    async def fake_gpt(prompt, model=None, system=None, **kwargs):
        return "gpt", 0, 0, 0.0

    async def fake_llama(prompt, model=None):
        return "llama"

    from app import gpt_client, llama_integration

    monkeypatch.setattr(gpt_client, "ask_gpt", fake_gpt)
    monkeypatch.setattr(llama_integration, "ask_llama", fake_llama)

    long_prompt = "word " * 31
    assert asyncio.run(router.route_prompt(long_prompt, user_id="u")) == "gpt"

    kw_prompt = "please analyze this"
    assert asyncio.run(router.route_prompt(kw_prompt, user_id="u")) == "gpt"


def test_skill_metrics(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import analytics, router

    class DummySkill:
        name = "dummy"

        async def handle(self, prompt):
            return "done"

    monkeypatch.setattr(router, "CATALOG", [(["dummy"], DummySkill)])
    analytics._metrics = {
        "total": 0,
        "llama": 0,
        "gpt": 0,
        "fallback": 0,
        "session_count": 0,
        "transcribe_ms": 0,
        "transcribe_count": 0,
        "transcribe_errors": 0,
    }
    result = asyncio.run(router.route_prompt("dummy task", user_id="u"))
    assert result == "done"
    m = analytics.get_metrics()
    assert m["total"] == 1
    assert m["gpt"] == 0
    assert m["llama"] == 0


def test_debug_env_toggle(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router

    async def fake_gpt(prompt, model=None, system=None, **kwargs):
        return "ok", 0, 0, 0.0

    monkeypatch.setattr(router, "ask_gpt", fake_gpt)

    async def handle_cmd(prompt):
        return None

    monkeypatch.setattr(router, "handle_command", handle_cmd)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(router, "LLAMA_HEALTHY", False)
    monkeypatch.setattr(router.memgpt, "store_interaction", lambda *a, **k: None)
    monkeypatch.setattr(router, "add_user_memory", lambda *a, **k: None)
    monkeypatch.setattr(
        router, "cache_answer", lambda prompt, answer, cache_id=None: None
    )

    flags = []

    def fake_build(prompt, **kwargs):
        flags.append(kwargs.get("debug"))
        return "p", 0

    monkeypatch.setattr(router.PromptBuilder, "build", staticmethod(fake_build))

    monkeypatch.setenv("DEBUG", "0")
    asyncio.run(router.route_prompt("hello world", user_id="u"))
    monkeypatch.setenv("DEBUG", "1")
    asyncio.run(router.route_prompt("hello world", user_id="u"))

    assert flags == [False, True]


def test_llama_circuit_open(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import llama_integration, router

    monkeypatch.setattr(router, "llama_circuit_open", False)
    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", False)
    monkeypatch.setattr(router, "handle_command", lambda p: None)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(
        router, "pick_model", lambda *a, **k: ("llama", "llama3", "light_default", None)
    )
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(router.PromptBuilder, "build", lambda *a, **k: (a[0], 0))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(router.route_prompt("hi", user_id="u"))
    assert exc.value.status_code == 503
    assert exc.value.detail == "LLaMA circuit open"


def test_generation_options_passthrough(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router

    monkeypatch.setattr(router, "llama_circuit_open", False)

    async def _hc(p):
        return None

    monkeypatch.setattr(router, "handle_command", _hc)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(
        router, "pick_model", lambda *a, **k: ("llama", "llama3", "light_default", None)
    )
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(router, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(router.memgpt, "store_interaction", lambda *a, **k: None)
    monkeypatch.setattr(router, "add_user_memory", lambda *a, **k: None)
    monkeypatch.setattr(
        router, "cache_answer", lambda prompt, answer, cache_id=None: None
    )

    captured: dict[str, Any] = {}

    async def fake_llama(prompt, model=None, **opts):
        captured.update(opts)
        yield "ok"

    monkeypatch.setattr(router, "ask_llama", fake_llama)

    result = asyncio.run(
        router.route_prompt(
            "hi",
            user_id="u",
            temperature=0.4,
            top_p=0.8,
        )
    )
    assert result == "ok"
    assert captured == {"temperature": 0.4, "top_p": 0.8}
