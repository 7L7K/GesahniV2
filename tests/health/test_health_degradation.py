import os

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_healthz_degrades_when_deps_missing(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    import app.health_utils as hu
    from app.api import health

    async def bad_check_llama():
        raise RuntimeError("down")

    async def bad_check_ha():
        raise RuntimeError("down")

    monkeypatch.setattr(hu, "check_llama", bad_check_llama)
    monkeypatch.setattr(hu, "check_home_assistant", bad_check_ha)

    app = FastAPI()
    app.include_router(health.router)
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["services"]["llama"] == "down"
    assert res.json()["services"]["ha"] == "down"
