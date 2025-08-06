import os

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_healthz(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    from app import status, llama_integration, home_assistant

    async def fake_status():
        return {"status": "healthy", "latency_ms": 1}

    monkeypatch.setattr(home_assistant, "startup_check", lambda: None)
    monkeypatch.setattr(llama_integration, "startup_check", lambda: None)
    monkeypatch.setattr(status, "llama_get_status", fake_status)

    app = FastAPI()
    app.include_router(status.router)
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["llama"] == "healthy"
