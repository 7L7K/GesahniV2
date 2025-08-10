import os
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_healthz_degrades_when_deps_missing(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    from app import status, llama_integration

    async def bad_status():
        raise RuntimeError("down")

    monkeypatch.setattr(status, "llama_get_status", bad_status)

    app = FastAPI()
    app.include_router(status.router, prefix="/v1")
    client = TestClient(app)
    res = client.get("/v1/healthz")
    assert res.status_code == 200
    assert res.json()["llama"] == "error"


