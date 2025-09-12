import pytest
from starlette.testclient import TestClient

from app.main import app


def make_client(monkeypatch):
    client = TestClient(app)
    # Ensure tests run in non-testing mode to hit actual validation logic
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_RUNNING", raising=False)
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("JWT_OPTIONAL_IN_TESTS", raising=False)
    return client


def test_missing_code_or_state(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/auth/callback", follow_redirects=False)
    assert resp.status_code == 400
    assert resp.json().get("detail") in ("missing_code_or_state",)


def test_state_mismatch(monkeypatch):
    client = make_client(monkeypatch)
    # Set different state cookie than query param
    client.cookies.set("g_state", "otherstate")
    client.cookies.set("g_code_verifier", "v" * 43)
    resp = client.get("/auth/callback?code=abc&state=stateval", follow_redirects=False)
    assert resp.status_code == 400
    assert resp.json().get("detail") in ("state_mismatch",)


def test_token_exchange_raises(monkeypatch):
    client = make_client(monkeypatch)
    # Enable dev mode to bypass state validation so we can test token exchange failure
    monkeypatch.setenv("DEV_MODE", "1")
    # Provide cookies that match
    client.cookies.set("g_state", "stateval")
    client.cookies.set("g_code_verifier", "v" * 43)

    async def _exchange(code, state, verify_state=False, code_verifier=None):
        raise Exception("network_error")

    monkeypatch.setattr("app.integrations.google.oauth.exchange_code", _exchange)

    resp = client.get("/auth/callback?code=abc&state=stateval", follow_redirects=False)
    # Should return 500 sanitized error
    assert resp.status_code == 500
    assert resp.json().get("detail") == "oauth_exchange_failed"


def test_monitor_raising_does_not_break_success(monkeypatch):
    client = make_client(monkeypatch)
    monkeypatch.setenv("DEV_MODE", "1")

    class DummyCreds:
        token = "at"
        refresh_token = "rt"
        id_token = "idtoken"

    async def _exchange(code, state, verify_state=False, code_verifier=None):
        return DummyCreds()

    monkeypatch.setattr("app.integrations.google.oauth.exchange_code", _exchange)

    # Make monitor return an object that raises on record()
    class BadMon:
        def record(self, success: bool):
            raise Exception("monitor_failure")

    monkeypatch.setattr("app.api.google_oauth._get_oauth_monitor", lambda: BadMon())

    client.cookies.set("g_state", "stateval")
    client.cookies.set("g_code_verifier", "v" * 43)

    # Ensure id_token decoding yields issuer/sub/email so callback proceeds
    monkeypatch.setattr(
        "app.api.google_oauth.jwt_decode",
        lambda token, options=None: {"iss": "https://accounts.google.com", "sub": "subid", "email": "user@example.com"},
    )

    resp = client.get("/auth/callback?code=abc&state=stateval", follow_redirects=False)
    assert resp.status_code in (302, 303)


