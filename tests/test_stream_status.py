import os
import sys

from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_app(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    return main


def test_streaming_sets_status_code(monkeypatch):
    main = setup_app(monkeypatch)

    async def fail(*args, **kwargs):
        raise HTTPException(status_code=418, detail="teapot")

    monkeypatch.setattr(main, "route_prompt", fail)

    client = TestClient(main.app)
    resp = client.post("/ask", json={"prompt": "hi"})
    assert resp.status_code == 418
    assert resp.text == "[error:teapot]"
