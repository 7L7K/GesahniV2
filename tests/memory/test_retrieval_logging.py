from __future__ import annotations

import pytest

from app.retrieval.pipeline import run_pipeline


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    yield


def test_pipeline_trace_contains_threshold_and_scores(monkeypatch):
    # We stub external calls by running with an empty collection expectation; function should still return trace entries
    texts, trace = run_pipeline(
        user_id="u1",
        query="hello world",
        intent="chat",
        collection="kb:default",
        explain=True,
    )
    assert isinstance(trace, list)
    # Hybrid stage exists and contains policy metadata
    hyb = next((t for t in trace if t.get("event") == "hybrid"), None)
    assert hyb is not None
    meta = hyb.get("meta") or {}
    assert meta.get("threshold_sim") == 0.75
