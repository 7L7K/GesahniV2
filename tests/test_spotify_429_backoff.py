import pytest

@pytest.mark.asyncio
async def test_429_bubbles_retry_after(monkeypatch, app_client, seed_spotify_token):
    from app.integrations.spotify import client as sp

    async def fake_put(self, path, **kwargs):
        class R:
            status_code = 429
            headers = {"Retry-After": "2"}
            def json(self): return {}
        return R()

    monkeypatch.setattr(sp.SpotifyClient, "_proxy_request", fake_put, raising=True)

    r = await app_client.post("/v1/spotify/play", json={"uris": ["spotify:track:4cOdK2wGLETKBW3PvgPWqT"]})
    assert r.status_code == 429
    assert r.headers.get("Retry-After") in {"2", 2}


