import os, sys
from fastapi.testclient import TestClient
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_app(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    os.environ["ADMIN_TOKEN"] = "secret"
    os.environ["OPENAI_API_KEY"] = "key"
    os.environ["OPENAI_MODEL"] = "gpt"
    import app.home_assistant as home_assistant
    import app.llama_integration as llama_integration
    import app.status as status
    import app.main as main
    reload(home_assistant)
    reload(llama_integration)
    reload(status)
    reload(main)
    monkeypatch.setattr(home_assistant, "startup_check", lambda: None)
    monkeypatch.setattr(llama_integration, "startup_check", lambda: None)
    return main


def test_config_forbidden(monkeypatch):
    main = setup_app(monkeypatch)
    client = TestClient(main.app)
    resp = client.get("/config")
    assert resp.status_code == 403


def test_config_allowed(monkeypatch):
    main = setup_app(monkeypatch)
    client = TestClient(main.app)
    resp = client.get("/config", params={"token": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["OLLAMA_URL"] == "http://x"
    assert data["SIM_THRESHOLD"] == "0.90"
