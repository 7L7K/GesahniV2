import jwt
from datetime import datetime, timedelta
from typing import Any
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

import app.security as security
import app.deps.user as user_deps


def _build_client(monkeypatch):
    monkeypatch.setattr(security, "API_TOKEN", "secret")
    monkeypatch.setattr(security, "JWT_SECRET", "secret")
    monkeypatch.setattr(user_deps, "JWT_SECRET", "secret")
    monkeypatch.setattr(security, "_http_requests", {})
    monkeypatch.setattr(security, "_ws_requests", {})
    monkeypatch.setenv("JWT_SECRET", "secret")

    app = FastAPI()
    captured: dict[str, Any] = {}

    @app.post("/login")
    def login():
        exp = datetime.utcnow() + timedelta(minutes=5)
        token = jwt.encode(
            {"user_id": "alice", "exp": exp}, "secret", algorithm="HS256"
        )
        return {"access_token": token}

    @app.post("/capture/start")
    async def capture_start(
        request: Request,
        _: None = Depends(security.verify_token),
        __: None = Depends(security.rate_limit),
        _user_id: str = Depends(user_deps.get_current_user_id),
    ):
        captured["user_id"] = request.state.user_id
        captured["payload"] = request.state.jwt_payload
        return {"ok": True}

    client = TestClient(app)
    return client, captured


def test_capture_start_sets_user_id_from_token(monkeypatch):
    client, captured = _build_client(monkeypatch)
    token = client.post("/login").json()["access_token"]
    resp = client.post("/capture/start", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert captured["user_id"] == "alice"
    assert captured["payload"]["user_id"] == "alice"


def test_capture_start_invalid_token(monkeypatch):
    client, _ = _build_client(monkeypatch)
    exp = datetime.utcnow() - timedelta(minutes=5)
    token = jwt.encode({"user_id": "alice", "exp": exp}, "secret", algorithm="HS256")
    resp = client.post("/capture/start", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
