import pytest


@pytest.mark.asyncio
async def test_me_refreshes_on_401(monkeypatch, async_client, seed_spotify_token):
    # Arrange: make first GET /me return 401, second 200
    from app.integrations.spotify import client as sp

    calls = {"n": 0}

    async def fake_get(self, path, **kwargs):
        calls["n"] += 1

        class R:
            status_code = 401 if calls["n"] == 1 else 200

            def json(self):
                return {"id": "user"}

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise Exception("boom")

        return R()

    monkeypatch.setattr(sp.SpotifyClient, "_proxy_request", fake_get, raising=True)

    # Act
    r = await async_client.get("/v1/spotify/status")
    # Assert: your status route should succeed after refresh; adjust if different route
    assert r.status_code in (200, 204)
