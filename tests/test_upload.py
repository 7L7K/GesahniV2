import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient


def test_upload_endpoint(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import main, upload

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)

    async def fake_upload(file):
        return {"file": file.filename}

    monkeypatch.setattr(main, "upload_file", fake_upload)

    client = TestClient(main.app)
    resp = client.post("/upload", files={"file": ("a.wav", b"data")})
    assert resp.status_code == 200
    assert resp.json() == {"file": "a.wav"}
