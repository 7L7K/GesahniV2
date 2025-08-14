from http import HTTPStatus
import time
import jwt
from fastapi.testclient import TestClient

from app.main import app


def _mint(secret: str, sub: str, ttl_s: int = 300) -> str:
    now = int(time.time())
    payload = {"user_id": sub, "sub": sub, "iat": now, "exp": now + ttl_s}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_cookie_preferred_over_header_when_both_valid(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    c = TestClient(app)
    cookie_tok = _mint("secret", "cookie_user")
    header_tok = _mint("secret", "header_user")
    c.cookies.set("access_token", cookie_tok)
    r = c.get("/v1/whoami", headers={"Authorization": f"Bearer {header_tok}"})
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert body["is_authenticated"] is True
    assert body["session_ready"] is True
    assert body["source"] == "cookie"
    assert body["user"]["id"] == "cookie_user"


