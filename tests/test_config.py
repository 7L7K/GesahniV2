import os
import sys
from fastapi.testclient import TestClient
from importlib import reload
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_app(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    os.environ["ADMIN_TOKEN"] = "secret"

    os.environ["OPENAI_API_KEY"] = "key"
    os.environ["OPENAI_MODEL"] = "gpt"
    os.environ["SIM_THRESHOLD"] = "0.90"
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

def test_key():
    print("👀 OPENAI_API_KEY =", os.getenv("OPENAI_API_KEY"))
    assert os.getenv("OPENAI_API_KEY", "").startswith("sk-")

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


def test_config_env_reload(monkeypatch):
    env = Path(".env")
    env.write_text("ADMIN_TOKEN=secret\nDEBUG=0\n")
    main = setup_app(monkeypatch)
    client = TestClient(main.app)
    resp = client.get("/config", params={"token": "secret"})
    assert resp.json()["DEBUG"] == "0"
    env.write_text("ADMIN_TOKEN=secret\nDEBUG=1\n")
    time.sleep(0.1)
    resp = client.get("/config", params={"token": "secret"})
    assert resp.json()["DEBUG"] == "1"
    env.unlink()
    data = resp.json()
    assert data["SIM_THRESHOLD"] == "0.90"
