import sys
import types


# Provide a minimal chromadb stub so prompt_builder can be imported without the heavy dependency.
class _DummyCollection:
    def add(self, *a, **k):
        pass

    def query(self, *a, **k):
        return {"documents": [[]], "ids": [[]], "metadatas": [[]]}

    def upsert(self, *a, **k):
        pass

    def update(self, *a, **k):
        pass

    def delete(self, *a, **k):
        pass


class _DummyClient:
    def __init__(self, *a, **k):
        pass

    def get_or_create_collection(self, *a, **k):
        return _DummyCollection()


chromadb_stub = types.SimpleNamespace(
    Client=lambda *a, **k: _DummyClient(),
    PersistentClient=lambda *a, **k: _DummyClient(),
)
sys.modules.setdefault("chromadb", chromadb_stub)


class _Settings:
    def __init__(self, *a, **k):
        pass


sys.modules.setdefault("chromadb.config", types.SimpleNamespace(Settings=_Settings))
sys.modules.setdefault(
    "chromadb.utils.embedding_functions",
    types.SimpleNamespace(EmbeddingFunction=object),
)

from app import prompt_builder  # noqa: E402
from app.prompt_builder import MAX_PROMPT_TOKENS, PromptBuilder  # noqa: E402


def test_prompt_builder_respects_token_limit(monkeypatch):
    big = "token " * 12000
    monkeypatch.setattr(
        prompt_builder.memgpt, "summarize_session", lambda sid, user_id=None: big
    )
    monkeypatch.setattr(
        prompt_builder, "safe_query_user_memories", lambda uid, q, k=5: [big, big]
    )

    prompt, tokens = PromptBuilder.build("hi", session_id="s", user_id="u")
    assert tokens <= MAX_PROMPT_TOKENS


def test_prompt_builder_includes_user_prompt(monkeypatch):
    monkeypatch.setattr(
        prompt_builder.memgpt, "summarize_session", lambda sid, user_id=None: ""
    )
    monkeypatch.setattr(
        prompt_builder, "safe_query_user_memories", lambda uid, q, k=5: []
    )
    user_msg = "what is the weather?"
    prompt, _ = PromptBuilder.build(user_msg, session_id="s", user_id="u")
    assert user_msg in prompt


def test_prompt_builder_fills_all_fields(monkeypatch):
    monkeypatch.setattr(
        prompt_builder.memgpt,
        "summarize_session",
        lambda sid, user_id=None: "a summary",
    )
    monkeypatch.setattr(
        prompt_builder,
        "safe_query_user_memories",
        lambda uid, q, k=5: ["memory1", "memory2"],
    )
    prompt, _ = PromptBuilder.build(
        "question?",
        session_id="s",
        user_id="u",
        custom_instructions="be concise",
        debug=True,
        debug_info="DBG",
    )
    assert "a summary" in prompt
    assert "memory1" in prompt and "memory2" in prompt
    assert "be concise" in prompt
    assert "DBG" in prompt
    assert "question?" in prompt
    assert "{{" not in prompt


def test_prompt_builder_drops_summary_before_memories(monkeypatch):
    monkeypatch.setattr(
        prompt_builder,
        "_prompt_core",
        lambda: "{{conversation_summary}} {{memories}} {{user_prompt}}",
    )
    monkeypatch.setattr(prompt_builder, "count_tokens", lambda text: len(text))
    monkeypatch.setattr(prompt_builder, "MAX_PROMPT_TOKENS", 50)
    monkeypatch.setattr(
        prompt_builder.memgpt,
        "summarize_session",
        lambda sid, user_id=None: "S" * 40,
    )
    monkeypatch.setattr(
        prompt_builder, "safe_query_user_memories", lambda uid, q, k=5: ["M" * 30]
    )
    prompt, _ = PromptBuilder.build("hi", session_id="s", user_id="u")
    assert "S" * 40 not in prompt
    assert "M" * 30 in prompt
