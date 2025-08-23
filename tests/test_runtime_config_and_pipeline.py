from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.config_runtime import get_config
from app.main import app
from app.memory.memgpt.contracts import MemoryClaim
from app.memory.memgpt.policy import inject_for_task
from app.memory.rerankers.local_cross_encoder import MiniLMCrossEncoder
from app.prompt_builder import PromptBuilder
from app.telemetry import LogRecord, log_record_var


def test_runtime_config_defaults_loaded():
    cfg = get_config()
    d = cfg.to_dict()
    assert d["store"]["vector_store"] in {"chroma", "memory", "qdrant"}
    assert isinstance(d["retrieval"]["topk_vec"], int)
    assert isinstance(d["rerank"]["cascade"], bool)
    assert isinstance(d["memgpt"]["importance_tau"], float)
    assert isinstance(d["obs"]["ablation_flags"], list)


def test_admin_config_endpoint():
    client = TestClient(app)
    r = client.get("/v1/admin/config")
    assert r.status_code == 200
    body = r.json()
    assert "store" in body and "retrieval" in body


def test_status_vector_store_endpoint():
    client = TestClient(app)
    r = client.get("/v1/status/vector_store")
    assert r.status_code == 200
    body = r.json()
    assert "avg_latency_ms" in body and "sample_size" in body


def test_admin_retrieval_trace_endpoint(monkeypatch):
    from app.memory import vector_store as vs

    def _fake_search(user_id: str, prompt: str, k: int | None = None, filters=None):
        return [
            "alpha beta gamma",
            "beta delta",
            "epsilon zeta",
        ][: (k or 3)]

    monkeypatch.setattr(vs, "safe_query_user_memories", _fake_search)
    os.environ["USE_RETRIEVAL_PIPELINE"] = "1"
    client = TestClient(app)
    r = client.get("/v1/admin/retrieval/trace", params={"q": "beta", "k": 3})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("items"), list)
    assert isinstance(body.get("trace"), dict)
    assert "summary" in body["trace"]


def test_prompt_builder_uses_pipeline_when_enabled(monkeypatch):
    # Arrange tracing context
    rec = LogRecord(req_id="t1")
    log_record_var.set(rec)

    # Fake retrieval results
    from app.memory import vector_store as vs

    def _fake_search(user_id: str, prompt: str, k: int | None = None, filters=None):
        return [f"doc{i}" for i in range(10)]

    monkeypatch.setattr(vs, "safe_query_user_memories", _fake_search)
    os.environ["USE_RETRIEVAL_PIPELINE"] = "1"
    os.environ["TOPK_FINAL"] = "4"

    built, tokens = PromptBuilder.build("hello world", user_id="u", session_id="s")
    # route_trace should be populated with why-logs, and only 4 docs injected
    trace = getattr(rec, "route_trace", None) or []
    assert any(isinstance(t, dict) and "summary" in t for t in trace)


def test_reranker_minilm_orders_overlap():
    rr = MiniLMCrossEncoder()
    docs = ["foo bar baz", "bar qux", "something else"]
    scores = rr.rerank("bar", docs, top_k=3)
    # doc with "bar qux" or "foo bar baz" should be on top
    assert scores[0].index in {0, 1}


def test_memgpt_policy_injects_by_threshold():
    claims = [
        MemoryClaim(
            claim="likes jazz", evidence=["conv1"], confidence=0.8, horizons=["long"]
        ),
        MemoryClaim(
            claim="iffy note", evidence=["conv2"], confidence=0.4, horizons=["short"]
        ),
    ]
    out = inject_for_task("chat", claims)
    assert "likes jazz" in out and "iffy note" not in out
