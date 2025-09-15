import pytest

from app import prompt_builder
from app.memory import api as memory_api
from app.memory.env_utils import DEFAULT_MEM_TOP_K
from app.prompt_builder import PromptBuilder


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, DEFAULT_MEM_TOP_K),
        ("", DEFAULT_MEM_TOP_K),
        ("3", 3),
        (0, DEFAULT_MEM_TOP_K),
    ],
)
def test_coerce_k(monkeypatch, raw, expected):
    monkeypatch.setattr(memory_api, "_get_mem_top_k", lambda: DEFAULT_MEM_TOP_K)
    assert memory_api._coerce_k(raw) == expected


@pytest.mark.asyncio
async def test_build_sanitizes_top_k(monkeypatch):
    monkeypatch.setattr(
        prompt_builder.memgpt, "summarize_session", lambda sid, user_id=None: ""
    )
    monkeypatch.setattr(prompt_builder, "_get_mem_top_k", lambda: "0")
    monkeypatch.setattr(memory_api, "_get_mem_top_k", lambda: DEFAULT_MEM_TOP_K)

    captured = {}

    class DummyStore:
        def query_user_memories(self, user_id, prompt, k):
            captured["k"] = k
            return []

    monkeypatch.setattr(memory_api, "_store", DummyStore())

    PromptBuilder.build("hello", session_id="s", user_id="u")
    assert captured["k"] == DEFAULT_MEM_TOP_K
