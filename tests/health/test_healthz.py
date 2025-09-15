import os

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_healthz(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    import app.health_utils as hu
    from app import home_assistant, llama_integration, status
    from app.api import health

    async def fake_status():
        return {"status": "healthy", "latency_ms": 1}

    async def fake_check_llama():
        return "ok"

    async def fake_check_ha():
        return "ok"

    monkeypatch.setattr(home_assistant, "startup_check", lambda: None)
    monkeypatch.setattr(llama_integration, "startup_check", lambda: None)
    monkeypatch.setattr(status, "llama_get_status", fake_status)
    monkeypatch.setattr(hu, "check_llama", fake_check_llama)
    monkeypatch.setattr(hu, "check_home_assistant", fake_check_ha)

    app = FastAPI()
    app.include_router(health.router)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["services"]["llama"] == "up"
