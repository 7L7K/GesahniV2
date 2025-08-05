import os
import jwt
from fastapi.testclient import TestClient


def setup_app(monkeypatch, tmp_path):
    os.environ.setdefault("OLLAMA_URL", "http://x")
    os.environ.setdefault("OLLAMA_MODEL", "llama3")
    os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
    os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
    os.environ["JWT_SECRET"] = "secret"
    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    monkeypatch.setattr(main, "SESSIONS_DIR", tmp_path)
    return main


def test_websocket_transcription(monkeypatch, tmp_path):
    main = setup_app(monkeypatch, tmp_path)

    async def fake_transcribe(path: str) -> str:
        return "hello"

    monkeypatch.setattr(main, "transcribe_file", fake_transcribe)

    client = TestClient(main.app)
    token = jwt.encode({"user_id": "tester"}, "secret", algorithm="HS256")
    with client.websocket_connect(
        "/transcribe", headers={"Authorization": f"Bearer {token}"}
    ) as ws:
        ws.send_json({"rate": 16000})
        ws.send_bytes(b"audio")
        data = ws.receive_json()
        assert data["text"] == "hello"
        session_id = data["session_id"]
        ws.send_text("end")

    audio_path = tmp_path / session_id / "stream.wav"
    assert audio_path.exists()
    assert audio_path.read_bytes() == b"audio"
