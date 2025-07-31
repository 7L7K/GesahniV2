import json
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.main import app
import app.session_manager as sm
import app.tasks as tasks
import app.main as main


def setup_temp(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(tasks, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(main, "SESSIONS_DIR", tmp_path)


def test_capture_flow(monkeypatch, tmp_path):
    setup_temp(monkeypatch, tmp_path)
    client = TestClient(app)

    resp = client.post("/capture/start")
    assert resp.status_code == 200
    data = resp.json()
    session_id = data["session_id"]
    sess_dir = tmp_path / session_id
    assert sess_dir.exists()

    files = {"audio": ("a.wav", b"data")}
    resp = client.post(
        "/capture/save",
        data={"session_id": session_id, "transcript": "hello world"},
        files=files,
    )
    assert resp.status_code == 200

    resp = client.post("/capture/tags", data={"session_id": session_id})
    assert resp.status_code == 200

    tag_file = sess_dir / "tags.json"
    assert tag_file.exists()
    tags = json.loads(tag_file.read_text())
    assert "hello" in tags

    resp = client.get("/search/sessions", params={"q": "hello"})
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["session_id"] == session_id for r in results)
