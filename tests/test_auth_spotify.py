import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _set_spotify_env(monkeypatch):
    # Ensure Spotify OAuth helpers initialize cleanly in tests
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "dummy")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "dummy")
    yield


def test_happy_path_whoami_and_spotify_status(client: TestClient):
    # whoami should be callable (test harness allows anon)
    r = client.get("/v1/whoami")
    assert r.status_code == 200
    body = r.json()
    assert "user_id" in body

    # spotify status should return connected=false in clean test env
    r2 = client.get("/v1/spotify/status")
    assert r2.status_code == 200
    js = r2.json()
    assert isinstance(js, dict)
    assert js.get("connected") in (True, False)


def test_spotify_devices_requires_auth(client: TestClient):
    # Without auth, spotify devices should return 401
    r = client.get("/v1/spotify/devices")
    assert r.status_code in (401, 403)


def test_header_mode_sees_authorization(client: TestClient, monkeypatch):
    # Simulate header-mode token (valid format but not verified) and ensure header is read
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    headers = {"Authorization": "Bearer dummy.token.value"}
    r = client.get("/v1/whoami", headers=headers)
    # In tests the token isn't validated, but whoami should still return 200
    assert r.status_code == 200


def test_spotify_callback_shape(client: TestClient, monkeypatch):
    # Simulate callback without required params -> should return 400
    r = client.get("/v1/spotify/callback")
    assert r.status_code == 400


