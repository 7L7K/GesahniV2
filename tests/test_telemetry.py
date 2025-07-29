import os, sys, json
from fastapi.testclient import TestClient
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def setup_app(monkeypatch, hist_path):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import main
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    monkeypatch.setattr("app.history.HISTORY_FILE", hist_path)
    async def fake_route(prompt: str, model=None):
        return "ok"
    monkeypatch.setattr(main, "route_prompt", fake_route)
    return TestClient(main.app)


def test_telemetry_logged(monkeypatch, tmp_path):
    hist = tmp_path / "hist.jsonl"
    client = setup_app(monkeypatch, str(hist))
    resp = client.post("/ask", json={"prompt": "hi"})
    assert resp.status_code == 200
    line = hist.read_text().splitlines()[-1]
    data = json.loads(line)
    assert data["status"] == "OK"
    assert data["latency_ms"] >= 0
