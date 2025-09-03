import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    # Ensure scope enforcement active in tests
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    yield


def test_spotify_devices_allows_music_control_scope(monkeypatch):
    # Patch Spotify client to avoid network calls
    import app.api.spotify_player as sp

    async def _fake_get_devices(self):
        return []

    monkeypatch.setattr(
        sp.SpotifyClient, "get_devices", _fake_get_devices, raising=False
    )

    from app.main import app

    client = TestClient(app)

    # Mint access token with required scope
    from app.tokens import make_access

    token = make_access({"user_id": "u1", "scopes": ["music:control"]})

    r = client.get("/v1/spotify/devices", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
