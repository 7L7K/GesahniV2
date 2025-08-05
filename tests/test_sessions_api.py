import os
import json
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")

from app.main import app
import app.session_manager as sm
import app.tasks as tasks
import app.main as main
import app.history as history
from app.session_store import SessionStatus
import app.session_store as store


def setup_temp(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    monkeypatch.setattr(sm, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(tasks, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(main, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(store, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "history.jsonl")
    monkeypatch.setattr(sm, "append_history", history.append_history)
    monkeypatch.setenv("API_TOKEN", "secret")


def _headers() -> dict:
    token = jwt.encode({"user_id": "tester"}, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_capture_flow(monkeypatch, tmp_path):
    setup_temp(monkeypatch, tmp_path)
    client = TestClient(app)

    headers = _headers()
    resp = client.post("/capture/start", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    session_id = data["session_id"]
    sess_dir = tmp_path / session_id
    assert sess_dir.exists()

    files = {"audio": ("a.wav", b"data", "audio/wav")}
    resp = client.post(
        "/capture/save",
        data={"session_id": session_id, "transcript": "hello world"},
        files=files,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == SessionStatus.TRANSCRIBED.value

    async def fake_gpt(prompt, model=None, system=None):
        return "summary", 0, 0, 0

    monkeypatch.setattr(tasks, "ask_gpt", fake_gpt, raising=False)
    resp = client.post(f"/sessions/{session_id}/summarize", headers=headers)
    assert resp.status_code == 200

    tag_file = sess_dir / "tags.json"
    assert tag_file.exists()
    tags = json.loads(tag_file.read_text())
    assert "hello" in tags

    resp = client.get(
        "/search/sessions",
        params={"q": "hello", "sort": "recent", "page": 1, "limit": 10},
        headers=headers,
    )
    assert resp.status_code == 200
    results = resp.json()
    assert any(
        r["session_id"] == session_id and "snippet" in r and "created_at" in r
        for r in results
    )

    hist_file = tmp_path / "history.jsonl"
    assert hist_file.exists()
    lines = hist_file.read_text().strip().splitlines()
    capture_records = [
        json.loads(l) for l in lines if json.loads(l).get("type") == "capture"
    ]
    assert capture_records and capture_records[-1]["session_id"] == session_id


def test_search_sort_and_pagination(monkeypatch, tmp_path):
    setup_temp(monkeypatch, tmp_path)
    headers = _headers()
    for i in range(3):
        sid = f"2023-01-0{i+1}T00-00-00"
        sd = tmp_path / sid
        sd.mkdir()
        (sd / "transcript.txt").write_text("hello world", encoding="utf-8")
        (sd / "tags.json").write_text(json.dumps(["hello"]))
        meta = {
            "session_id": sid,
            "created_at": f"2023-01-0{i+1}T00:00:00Z",
            "status": SessionStatus.DONE.value,
        }
        (sd / "meta.json").write_text(json.dumps(meta))
    client = TestClient(app)
    resp = client.get(
        "/search/sessions",
        params={"q": "hello", "sort": "recent", "page": 2, "limit": 1},
        headers=headers,
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["session_id"] == "2023-01-02T00-00-00"


def test_search_by_tag(monkeypatch, tmp_path):
    setup_temp(monkeypatch, tmp_path)
    headers = _headers()
    sid = "tagonly"
    sd = tmp_path / sid
    sd.mkdir()
    (sd / "transcript.txt").write_text("nothing", encoding="utf-8")
    (sd / "tags.json").write_text(json.dumps(["special"]))
    meta = {
        "session_id": sid,
        "created_at": "2023-01-01T00:00:00Z",
        "status": SessionStatus.DONE.value,
    }
    (sd / "meta.json").write_text(json.dumps(meta))
    client = TestClient(app)
    resp = client.get(
        "/search/sessions",
        params={"q": "special"},
        headers=headers,
    )
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["session_id"] == sid for r in results)


def test_manual_pipeline(monkeypatch, tmp_path):
    setup_temp(monkeypatch, tmp_path)
    headers = _headers()
    client = TestClient(app)

    # create session and save only audio
    resp = client.post("/capture/start", headers=headers)
    session_id = resp.json()["session_id"]
    files = {"audio": ("a.wav", b"data", "audio/wav")}
    resp = client.post(
        "/capture/save", data={"session_id": session_id}, files=files, headers=headers
    )
    assert resp.json()["status"] == SessionStatus.PENDING.value

    # pending sessions listing
    resp = client.get(
        "/sessions", params={"status": SessionStatus.PENDING.value}, headers=headers
    )
    assert any(s["session_id"] == session_id for s in resp.json())

    monkeypatch.setattr(tasks, "sync_transcribe_file", lambda p: "hi there")
    resp = client.post(f"/sessions/{session_id}/transcribe", headers=headers)
    assert resp.status_code == 200
    assert sm.get_session_meta(session_id)["status"] == SessionStatus.TRANSCRIBED.value

    async def fake_gpt2(prompt, model=None, system=None):
        return "summary", 0, 0, 0

    monkeypatch.setattr(tasks, "ask_gpt", fake_gpt2, raising=False)
    resp = client.post(f"/sessions/{session_id}/summarize", headers=headers)
    assert resp.status_code == 200
    assert sm.get_session_meta(session_id)["status"] == SessionStatus.DONE.value
