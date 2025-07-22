import os, sys
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
os.environ.setdefault("HOME_ASSISTANT_URL", "http://test")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://test")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.status import router as status_router

app = FastAPI()
app.include_router(status_router)

@pytest.mark.asyncio
async def test_status_endpoint_combines_metrics(monkeypatch):
    async def mock_verify():
        return None
    async def mock_llama_status():
        return {"status":"healthy", "latency_ms":1}
    monkeypatch.setattr("app.status.verify_connection", mock_verify)
    monkeypatch.setattr("app.status.llama_status", mock_llama_status)
    client = TestClient(app)
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "backend" in data and "ha" in data and "llama" in data
