from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    yield


def client():
    return TestClient(app)


def test_ingest_markdown_text(monkeypatch):
    # Avoid requiring markitdown by calling lower-level function directly
    from app.ingest.markitdown_ingest import ingest_markdown_text

    text = "# Title\n\nSome content.\n\n## Section\n\nMore text."
    # When qdrant-client isn't available, this should raise RuntimeError; treat as skip
    try:
        res = ingest_markdown_text(user_id="u1", text=text, source="testdoc", collection="kb:test")
    except RuntimeError:
        pytest.skip("qdrant-client not installed")
    assert res["status"] in {"ok", "skipped"}
    assert "doc_hash" in res
    # chunk_count is > 0 on first ingest
    if res["status"] == "ok":
        assert res["chunk_count"] >= 1


