from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app
from tests.util_tokens import mint_jwt_token


def _auth_headers():
    tok = mint_jwt_token(sub="tester", secret="secret")
    return {"Authorization": f"Bearer {tok}"}


def test_sessions_legacy_wrapper(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    c = TestClient(app)
    r = c.get("/v1/sessions", headers=_auth_headers(), params={"legacy": 1})
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert isinstance(body, dict) and isinstance(body.get("items"), list)
