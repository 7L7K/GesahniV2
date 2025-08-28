import os
import urllib.parse as urlparse

import pytest
from fastapi.testclient import TestClient


def make_client(monkeypatch, tmp_path):
    # Minimal env for auth + spotify test mode
    monkeypatch.setenv("JWT_SECRET", "test-secret-123")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://testclient")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "x")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "y")
    monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "http://localhost:3000/callback")
    monkeypatch.setenv("SPOTIFY_TEST_MODE", "1")
    # TestClient uses http://testserver; keep it consistent for callback rewrite
    monkeypatch.setenv("BACKEND_URL", "http://testserver")
    # Isolate token DB per test
    monkeypatch.setenv(
        "THIRD_PARTY_TOKENS_DB", str(tmp_path / "third_party_tokens.db")
    )

    from app.main import app

    return TestClient(app)


def auth_login(client: TestClient, username: str = "testuser"):
    # Dev login flow: sets cookies and returns ok
    r = client.post("/v1/auth/login", params={"username": username})
    assert r.status_code == 200
    return r


def test_spotify_connect_callback_persists_and_status_connected(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    auth_login(client)

    # Start connect (Origin allowed)
    r = client.get(
        "/v1/spotify/connect",
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "authorize_url" in data

    # In test mode, authorize_url points to backend /v1/spotify/callback with code=fake
    auth_url = data["authorize_url"]
    parsed = urlparse.urlparse(auth_url)
    assert parsed.path.endswith("/v1/spotify/callback")

    # Follow callback
    cb = client.get(auth_url)
    # Callback redirects to frontend; status 302
    assert cb.status_code in (200, 302)

    # Verify status indicates connected
    st = client.get("/v1/spotify/status")
    assert st.status_code == 200, st.text
    assert st.json().get("connected") is True


def test_spotify_connect_origin_blocked(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    auth_login(client)

    # Evil origin and referer should be blocked
    r = client.get(
        "/v1/spotify/connect",
        headers={
            "Origin": "https://evil.example",
            "Referer": "https://evil.example/page",
        },
    )
    assert r.status_code == 403


def test_spotify_connect_rate_limit(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    auth_login(client, username="ratelimit-user")

    # Hit 11 times within minute; last should 429
    last = None
    for i in range(11):
        last = client.get(
            "/v1/spotify/connect",
            headers={"Origin": "http://localhost:3000"},
        )
    assert last is not None
    assert last.status_code == 429

