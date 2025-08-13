from __future__ import annotations

from fastapi.testclient import TestClient
from app.main import app


def test_health_qdrant_endpoint_present():
    c = TestClient(app)
    r = c.get("/v1/health/qdrant")
    assert r.status_code == 200
    assert "ok" in r.json()


def test_health_chroma_endpoint_present():
    c = TestClient(app)
    r = c.get("/v1/health/chroma")
    assert r.status_code == 200
    assert "ok" in r.json()

