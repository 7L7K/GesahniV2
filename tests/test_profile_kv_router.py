from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    yield


def client():
    return TestClient(app)


def test_profile_kv_short_ask_flow(monkeypatch):
    c = client()
    # 1) User states a fact
    r = c.post("/v1/ask", json={"prompt": "it's blue"})
    assert r.status_code == 200
    # 2) Immediately ask short profile question
    r2 = c.post("/v1/ask", json={"prompt": "what's my favorite color"})
    assert r2.status_code == 200
    assert "blue" in (r2.text or r2.content.decode("utf-8"))



