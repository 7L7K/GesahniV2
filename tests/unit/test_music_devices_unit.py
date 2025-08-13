import os
from fastapi.testclient import TestClient


def _auth():
    import jwt as _jwt
    token = _jwt.encode({"user_id": "u_test"}, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_devices_returns_empty_on_auth_error(monkeypatch):
    import app.api.music as music
    from app.main import app

    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setattr(music, "PROVIDER_SPOTIFY", True)

    class Boom(music.SpotifyClient):
        async def devices(self):  # type: ignore[override]
            raise music.SpotifyAuthError("nope")

    monkeypatch.setattr(music, "SpotifyClient", Boom)
    c = TestClient(app)
    out = c.get("/v1/music/devices", headers=_auth()).json()
    assert out["devices"] == []


