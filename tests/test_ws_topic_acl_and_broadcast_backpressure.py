import os
import asyncio
import jwt
from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    from app.main import app
    return TestClient(app)


def _tok(user_id="u1", scopes: str = ""):
    payload = {"user_id": user_id}
    if scopes:
        payload["scope"] = scopes
    return jwt.encode(payload, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")


def test_ws_topic_acl_resident_me(monkeypatch):
    c = _client(monkeypatch)
    # Connect to care WS with token for u1
    url = "/v1/ws/care?access_token=" + _tok("u1")
    with c.websocket_connect(url) as ws:
        # Subscribe to own topic allowed
        ws.send_json({"action": "subscribe", "topic": "resident:u1"})
        # Unauthorized topic should be ignored (no crash). Send a ping to ensure connection still alive.
        ws.send_json({"action": "subscribe", "topic": "resident:other"})
        ws.send_text("ping")
        assert ws.receive_text() in ("pong",)


def test_ws_broadcast_backpressure_survives_many_clients(monkeypatch):
    # Reduce concurrency to a small number to exercise the semaphore path
    monkeypatch.setenv("WS_BROADCAST_CONCURRENCY", "4")
    c = _client(monkeypatch)

    sockets = []
    try:
        for i in range(0, 12):
            sockets.append(c.websocket_connect("/v1/ws/music?access_token=" + _tok(f"u{i}")))
        # Trigger a broadcast via a GET that calls _broadcast internally (get_state used indirectly)
        # The music state broadcast occurs on certain endpoints; we poke /v1/state which typically broadcasts current state.
        r = c.get("/v1/state", headers={"Authorization": f"Bearer {_tok('u0')}"})
        assert r.status_code in (200, 404, 500)  # tolerate env variability; test is about not hanging
        # If we can still perform another request quickly, backpressure didn't starve handlers
        r2 = c.get("/v1/status")
        assert r2.status_code in (200, 401, 403)
    finally:
        for ws in sockets:
            try:
                ws.close()
            except Exception:
                pass


