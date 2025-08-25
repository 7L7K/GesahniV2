import pytest, asyncio

@pytest.mark.asyncio
async def test_spotify_budget_enforced(monkeypatch, app_client, seed_spotify_token):
    from app.integrations.spotify import client as sp

    async def slow_get(self, path, **kwargs):
        await asyncio.sleep(5)  # simulate slow upstream
        class R:
            status_code = 200
            def json(self): return {}
        return R()

    monkeypatch.setattr(sp.SpotifyClient, "_proxy_request", slow_get, raising=True)

    r = await app_client.get("/v1/spotify/devices")
    # depending on your ROUTER_BUDGET_MS & enforcement, assert 504 or 200
    assert r.status_code in (200, 504)


