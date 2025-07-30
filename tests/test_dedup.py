import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")

from fastapi.testclient import TestClient
from app import main


def test_dedup_middleware(monkeypatch):
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    client = TestClient(main.app)
    headers = {"X-Request-ID": "abc"}
    r1 = client.get("/health", headers=headers)
    assert r1.status_code == 200
    r2 = client.get("/health", headers=headers)
    assert r2.status_code == 409
