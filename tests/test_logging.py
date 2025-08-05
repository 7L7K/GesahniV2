import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest
from fastapi.testclient import TestClient

os.environ["OLLAMA_URL"] = "http://x"
os.environ["OLLAMA_MODEL"] = "llama3"
os.environ["HOME_ASSISTANT_URL"] = "http://ha"
os.environ["HOME_ASSISTANT_TOKEN"] = "token"
from app import main
from app.logging_config import configure_logging


def test_request_id_header(monkeypatch):
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    client = TestClient(main.app)
    resp = client.get("/health")
    assert "X-Request-ID" in resp.headers
