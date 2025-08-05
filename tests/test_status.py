import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest
from fastapi.testclient import TestClient


def test_status_endpoint(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import main, status, home_assistant, llama_integration

    async def fake_request(method, path, json=None, timeout=10.0):
        return {}

    async def fake_llama_status():
        return {"status": "healthy", "latency_ms": 1}

    monkeypatch.setattr(home_assistant, "startup_check", lambda: None)
    monkeypatch.setattr(llama_integration, "startup_check", lambda: None)
    monkeypatch.setattr(status, "_request", fake_request)
    monkeypatch.setattr(status, "llama_get_status", fake_llama_status)
    monkeypatch.setattr(
        status,
        "get_metrics",
        lambda: {
            "total": 1,
            "llama": 1,
            "gpt": 0,
            "fallback": 0,
            "session_count": 0,
            "transcribe_ms": 0,
            "transcribe_count": 0,
            "transcribe_errors": 0,
        },
    )

    client = TestClient(main.app)
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["backend"] == "ok"
    assert data["llama"] == "healthy"
    assert data["metrics"]["llama_hits"] == 1
