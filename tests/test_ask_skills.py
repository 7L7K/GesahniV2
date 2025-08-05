import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_app(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import main, router

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    called = {"llm": False}

    async def fake_llm(prompt, model=None, system=None):
        called["llm"] = True
        return "llm", 0, 0, 0.0

    monkeypatch.setattr(router, "ask_llama", fake_llm)
    monkeypatch.setattr(router, "ask_gpt", fake_llm)
    return main, called


def test_keyword_catalog_shortcuts(monkeypatch):
    main, called = setup_app(monkeypatch)
    client = TestClient(main.app)
    resp = client.post("/ask", json={"prompt": "2 + 2"})
    assert resp.status_code == 200
    assert resp.json()["response"] == "4"
    assert not called["llm"]
