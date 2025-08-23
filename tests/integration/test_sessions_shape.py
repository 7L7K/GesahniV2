from http import HTTPStatus

import jwt
from fastapi.testclient import TestClient

from app.main import app


def _auth_headers():
    tok = jwt.encode({"user_id": "tester"}, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def test_sessions_returns_array(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    c = TestClient(app)
    r = c.get("/v1/sessions", headers=_auth_headers())
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert isinstance(body, list), f"expected array, got {type(body)}"
    # Must not be { items: [...] } on canonical route
    assert not (
        isinstance(body, dict) and "items" in body
    ), "canonical /sessions must not wrap items"
