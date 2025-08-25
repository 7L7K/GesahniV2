import pytest

@pytest.mark.asyncio
async def test_login_starts_pkce(app_client):
    r = await app_client.get("/v1/spotify/login")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert "authorize_url" in j


@pytest.mark.asyncio
async def test_callback_requires_state(app_client):
    r = await app_client.get("/v1/spotify/callback?code=fake&state=bad")
    assert r.status_code == 400


