import os
from fastapi.testclient import TestClient


def setup_app(monkeypatch, tmp_path):
    os.environ.setdefault("OLLAMA_URL", "http://x")
    os.environ.setdefault("OLLAMA_MODEL", "llama3")
    os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
    os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
    os.environ.pop("API_TOKEN", None)
    from app import main

    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    monkeypatch.setattr(main, "SESSIONS_DIR", tmp_path)
    return main


def test_ws_user_ids_distinct(monkeypatch, tmp_path):
    main = setup_app(monkeypatch, tmp_path)

    async def fake_transcribe(path: str) -> str:
        rec = main.log_record_var.get()
        return rec.user_id if rec else "none"

    monkeypatch.setattr(main, "transcribe_file", fake_transcribe)

    client = TestClient(main.app)

    headers1 = {"Authorization": "Bearer one"}
    headers2 = {"Authorization": "Bearer two"}

    with client.websocket_connect("/transcribe", headers=headers1) as ws:
        ws.send_json({"rate": 16000})
        ws.send_bytes(b"a")
        data1 = ws.receive_json()
        ws.send_text("end")

    with client.websocket_connect("/transcribe", headers=headers2) as ws:
        ws.send_json({"rate": 16000})
        ws.send_bytes(b"a")
        data2 = ws.receive_json()
        ws.send_text("end")

    user1 = data1["text"]
    user2 = data2["text"]
    assert user1 == main._anon_user_id(headers1["Authorization"])
    assert user2 == main._anon_user_id(headers2["Authorization"])
    assert user1 != user2
