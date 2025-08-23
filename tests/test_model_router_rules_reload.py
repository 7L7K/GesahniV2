import asyncio
import os

import app.model_router as mr


def test_compose_cache_id_is_stable():
    prompt = "Hello World"
    docs = ["doc A", "doc B"]
    cid1 = mr.compose_cache_id("gpt-5-nano", prompt, docs)
    cid2 = mr.compose_cache_id("gpt-5-nano", prompt, list(reversed(docs)))
    cid3 = mr.compose_cache_id("gpt-4.1-nano", prompt, docs)
    assert cid1 == cid2
    assert cid1 != cid3


def test_route_text_short_default():
    d = mr.route_text(user_prompt="hi", prompt_tokens=2)
    assert d.model == "gpt-5-nano"
    assert d.reason == "default"


def test_route_text_long_prompt():
    long_prompt = "a" * 500
    d = mr.route_text(user_prompt=long_prompt, prompt_tokens=300)
    assert d.model == "gpt-4.1-nano"
    assert d.reason == "long-prompt"


def test_route_text_long_rag(monkeypatch):
    rules = mr._load_rules().copy()
    rules["RAG_LONG_CONTEXT_THRESHOLD"] = 20
    monkeypatch.setattr(mr, "_load_rules", lambda: rules)
    docs = ["word " * 30]
    d = mr.route_text(user_prompt="hi", retrieved_docs=docs)
    assert d.model == "gpt-4.1-nano"
    assert d.reason == "long-context"


def test_route_text_ops_simple_vs_complex():
    simple = mr.route_text(user_prompt="ops", intent="ops", ops_files_count=1)
    assert simple.model == "gpt-5-nano"
    assert simple.reason == "ops-simple"
    complex_d = mr.route_text(user_prompt="ops", intent="ops", ops_files_count=5)
    assert complex_d.model == "gpt-4.1-nano"
    assert complex_d.reason == "ops-complex"


def test_run_with_self_check_escalates_once():
    async def ask_stub(prompt, model, system, **kwargs):
        if model == "gpt-5-nano":
            return "not sure", 5, 1, 0.0
        return "because adequate detailed answer", 10, 2, 0.0

    text, model, reason, score, pt, ct, cost, escalated = asyncio.run(
        mr.run_with_self_check(
            ask_func=ask_stub,
            model="gpt-5-nano",
            user_prompt="hello",
            system_prompt=None,
            retrieved_docs=[],
            threshold=0.6,
            max_retries=1,
        )
    )
    assert model == "gpt-4.1-nano"
    assert reason == "self-check-escalation"
    assert escalated is True
    assert score >= 0.0


def test_load_rules_hot_reload(tmp_path, monkeypatch):
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        "MAX_SHORT_PROMPT_TOKENS: 1000\n"
        "RAG_LONG_CONTEXT_THRESHOLD: 6000\n"
        "DOC_LONG_REPLY_TARGET: 900\n"
        "OPS_MAX_FILES_SIMPLE: 2\n"
        "SELF_CHECK_FAIL_THRESHOLD: 0.60\n"
        "MAX_RETRIES_PER_REQUEST: 1\n"
    )
    monkeypatch.setattr(mr, "_RULES_PATH", rules_file)
    monkeypatch.setattr(mr, "_RULES_MTIME", None)
    monkeypatch.setattr(mr, "_LOADED_RULES", None)

    prompt = "x" * 200
    d1 = mr.route_text(user_prompt=prompt, prompt_tokens=200)
    assert d1.reason == "default"

    rules_file.write_text(
        "MAX_SHORT_PROMPT_TOKENS: 100\n"
        "RAG_LONG_CONTEXT_THRESHOLD: 6000\n"
        "DOC_LONG_REPLY_TARGET: 900\n"
        "OPS_MAX_FILES_SIMPLE: 2\n"
        "SELF_CHECK_FAIL_THRESHOLD: 0.60\n"
        "MAX_RETRIES_PER_REQUEST: 1\n"
    )
    st = rules_file.stat()
    os.utime(rules_file, (st.st_atime, st.st_mtime + 1))
    mr._RULES_MTIME = None
    mr._LOADED_RULES = None

    d2 = mr.route_text(user_prompt=prompt, prompt_tokens=200)
    assert d2.reason == "long-prompt"
    assert d2.model == "gpt-4.1-nano"
