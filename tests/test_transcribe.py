import os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient


def setup_app(monkeypatch, tmp_path):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    monkeypatch.setattr(main, "SESSIONS_DIR", tmp_path)
    return main


def test_transcribe_post_and_file_created(monkeypatch, tmp_path):
    main = setup_app(monkeypatch, tmp_path)

    async def fake_transcribe(path):
        return "hello"

    monkeypatch.setattr(main, "transcribe_file", fake_transcribe)
    client = TestClient(main.app)
    resp = client.post("/transcribe/123")
    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted"}
    transcript = tmp_path / "123" / "transcript.txt"
    assert transcript.read_text() == "hello"


def test_transcribe_get(monkeypatch, tmp_path):
    main = setup_app(monkeypatch, tmp_path)
    session = tmp_path / "abc"
    session.mkdir()
    (session / "transcript.txt").write_text("hi")
    client = TestClient(main.app)
    resp = client.get("/transcribe/abc")
    assert resp.status_code == 200
    assert resp.json() == {"text": "hi"}
