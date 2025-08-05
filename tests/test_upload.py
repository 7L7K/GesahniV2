import sys, os
import jwt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient


def test_upload_saves_file(tmp_path, monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    monkeypatch.setattr(main, "SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("API_TOKEN", "secret")

    client = TestClient(main.app)
    data = b"abc"
    token = jwt.encode({"user_id": "tester"}, "secret", algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/upload", files={"file": ("foo.wav", data, "audio/wav")}, headers=headers
    )
    assert resp.status_code == 200
    sid = resp.json()["session_id"]
    saved = tmp_path / sid / "source.wav"
    assert saved.exists()
    assert saved.read_bytes() == data
