import os, sys
from fastapi import FastAPI
from fastapi.testclient import TestClient
os.environ.setdefault("HOME_ASSISTANT_URL", "http://test")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://test")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.middleware import RequestIDMiddleware

app = FastAPI()
app.add_middleware(RequestIDMiddleware)

@app.get("/ping")
async def ping():
    return {"ok": True}

def test_logging_includes_request_id():
    client = TestClient(app)
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
