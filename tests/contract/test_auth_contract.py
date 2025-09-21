import re
import jwt
from httpx import AsyncClient

STATE = re.compile(r"state=([A-Za-z0-9\-_\.]+)")
CHAL = re.compile(r"code_challenge=([A-Za-z0-9\-_]+)")


async def test_jwt_claims_and_cookie_mode(async_client):
    r = await async_client.get("/v1/auth/whoami")
    assert r.json()["is_authenticated"] is False

    r = await async_client.post("/v1/auth/login", json={"username": "qazwsxppo", "password": "x"})
    assert r.status_code == 200

    r = await async_client.get("/v1/auth/whoami")
    j = r.json()
    assert j["is_authenticated"] is True
    # In cookie mode, server holds tokens; jwt-info exposes claims for debug:
    r2 = await async_client.get("/v1/auth/jwt-info")
    access_token = r2.json()["access_token"]
    assert "user_id" in access_token
    assert access_token["user_id"] == "qazwsxppo"


async def test_spotify_login_url(async_client):
    r = await async_client.get("/v1/auth/spotify/login_url")
    assert r.status_code == 200
    url = r.text  # Returns plain text URL, not JSON
    assert "response_type=code" in url
    assert STATE.search(url)
    assert CHAL.search(url)
