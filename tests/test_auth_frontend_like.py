import os

from fastapi.testclient import TestClient


def setup_app(monkeypatch):
    os.environ.setdefault("JWT_SECRET", "secret")
    from app import main

    # disable external startups
    monkeypatch.setattr(main, "ha_startup", lambda: None)
    monkeypatch.setattr(main, "llama_startup", lambda: None)
    return main.app


def test_ws_allows_query_param_token(monkeypatch):
    app = setup_app(monkeypatch)
    client = TestClient(app)

    import jwt
    token = jwt.encode({"user_id": "wsuser"}, "secret", algorithm="HS256")

    # The websocket route requires token; pass via query param to simulate browser
    with client.websocket_connect(f"/v1/transcribe?access_token={token}") as ws:
        # send a small text to let server progress through handshake
        ws.send_text("{}")
        # close cleanly
        ws.close()


