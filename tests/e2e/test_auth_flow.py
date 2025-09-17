"""Fast guard tests for auth behavior pinning."""

import asyncio

import pytest

BASE = "http://localhost:8000"


async def _login(client, user="dev"):
    r = await client.post(f"{BASE}/v1/auth/login", json={"username": user})
    r.raise_for_status()
    return r


@pytest.mark.asyncio
async def test_silent_refresh_cookie_flow(async_client):
    """Test that whoami triggers lazy refresh when access token expires."""
    # 1) login (cookies set)
    r = await _login(async_client)
    assert r.cookies.get("__session")

    # 2) force short access then wait to expire
    r = await async_client.get(f"{BASE}/v1/mock/set_access_cookie?max_age=1")
    assert r.status_code in (200, 204)
    await asyncio.sleep(2)

    # 3) whoami should trigger lazy refresh (still authenticated)
    r = await async_client.get(
        f"{BASE}/v1/whoami", headers={"X-Auth-Intent": "refresh"}
    )
    js = r.json()
    assert r.status_code == 200
    assert js["is_authenticated"] is True
    assert js["source"] in {"cookie", "header"}  # cookie wins if present


@pytest.mark.asyncio
async def test_refresh_requires_intent_when_cross_site(async_client, monkeypatch):
    """Test that refresh requires intent header when cross-site cookies enabled."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    await _login(async_client)
    # missing intent header
    r = await async_client.post(f"{BASE}/v1/auth/refresh")
    assert r.status_code == 400
    assert r.json().get("code") == "missing_intent_header_cross_site"
