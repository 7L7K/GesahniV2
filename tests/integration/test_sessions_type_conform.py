from http import HTTPStatus

import jwt
from fastapi.testclient import TestClient

from app.main import app


def _auth_headers():
    tok = jwt.encode({"user_id": "tester"}, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def test_sessions_type_conforms(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    c = TestClient(app)
    r = c.get("/v1/sessions", headers=_auth_headers())
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert isinstance(body, list)
    # Each item should have canonical fields
    for it in body:
        assert "session_id" in it
        assert "device_id" in it
        # optional fields
        assert "created_at" in it
        assert "last_seen_at" in it
        assert "current" in it


