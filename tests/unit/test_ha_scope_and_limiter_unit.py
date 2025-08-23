from importlib import reload

from fastapi.testclient import TestClient
from jose import jwt


def _app(monkeypatch):
    # Enforce JWT + scopes; tight rate limit to exercise 429 ordering
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_S", "60")
    # Fresh import so dependency order is applied
    import app.main as _main

    reload(_main)
    return _main.app


def _bearer(scope: str | None = None) -> dict:
    payload = {"user_id": "u1"}
    if scope:
        payload["scope"] = scope
    token = jwt.encode(payload, "testsecret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_ha_entities_401_without_token(monkeypatch):
    client = TestClient(_app(monkeypatch))
    r = client.get("/v1/ha/entities")
    assert r.status_code == 401


def test_ha_entities_403_without_scope(monkeypatch):
    client = TestClient(_app(monkeypatch))
    r = client.get("/v1/ha/entities", headers=_bearer())
    assert r.status_code == 403


def test_ha_entities_429_after_first_call(monkeypatch):
    client = TestClient(_app(monkeypatch))
    # First call with proper scope reaches handler (may be 500 if HA unconfigured)
    r1 = client.get("/v1/ha/entities", headers=_bearer("care:resident"))
    assert r1.status_code in {200, 400, 500}
    # Second call should be rate-limited (429) before handler executes
    r2 = client.get("/v1/ha/entities", headers=_bearer("care:resident"))
    assert r2.status_code == 429
