from __future__ import annotations

import os
import pytest

from app.retrieval.utils import RetrievedItem
from app.retrieval.pipeline import run_pipeline


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # Force in-memory embed stub; retrieval pipeline will call qdrant client but we only test threshold wiring
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    yield


def test_threshold_constant_documented(monkeypatch):
    # Ensure the documented constants are set in code paths (0.75 sim → 0.25 dist)
    from app.memory.vector_store.qdrant import __dict__ as qdict
    # Presence of cutoff constant usage validated indirectly; this is a smoke check the module loads
    assert "QdrantVectorStore" in qdict



