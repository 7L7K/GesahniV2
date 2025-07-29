import os, sys
import asyncio
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
    called = {"route": False}
    async def fake_route(prompt, model=None):
        called["route"] = True
        return "llm"
    monkeypatch.setattr(main, "route_prompt", fake_route)
    return main, called


def test_clock_skill_shortcuts(monkeypatch):
    main, called = setup_app(monkeypatch)
    client = TestClient(main.app)
    resp = client.post("/ask", json={"prompt": "what time is it?"})
    assert resp.status_code == 200
    assert "time" in resp.json()["response"].lower()
    assert not called["route"]
