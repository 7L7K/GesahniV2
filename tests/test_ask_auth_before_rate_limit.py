import os

import jwt
from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    monkeypatch.setenv("JWT_SECRET", "secret")
    # Ensure auth is required for /ask in this test
    monkeypatch.setenv("REQUIRE_JWT", "1")
    from app.main import app
    return TestClient(app)


def _token(user_id="u1"):
    return jwt.encode({"user_id": user_id}, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")


def test_ask_unauth_is_401_without_rl_headers(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/v1/ask", json={"prompt": "hello"})
    assert r.status_code == 401
    # Should not expose Retry-After when auth failed before limiter
    assert "Retry-After" not in r.headers


def test_ask_authed_over_limit_returns_429_with_retry_after(monkeypatch):
    c = _client(monkeypatch)
    tok = _token("u_rl")
    # Hit endpoint multiple times quickly to trigger long-window or burst limits
    headers = {"Authorization": f"Bearer {tok}", "Accept": "text/plain"}
    # We will make several requests; at least one should trip 429 with Retry-After
    got_429 = False
    for _ in range(0, 120):
        r = c.post("/v1/ask", json={"prompt": "hello"}, headers=headers)
        if r.status_code == 429:
            got_429 = True
            assert "Retry-After" in r.headers
            break
    assert got_429


