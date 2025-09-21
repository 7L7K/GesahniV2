import time

import pytest

from app.api.spotify import SpotifyApiError, refresh_spotify_tokens_for_user
from app.models.third_party_tokens import ThirdPartyToken


def test_spotify_refresh_requires_auth(client):
    client.cookies.clear()
    resp = client.post("/v1/spotify/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["refreshed"] is False
    assert body["reason"] == "not_authenticated"


def test_spotify_refresh_no_tokens(client):
    client.cookies.clear()
    login = client.post("/v1/auth/login", params={"username": "refresh-notokens"})
    assert login.status_code == 200

    resp = client.post("/v1/spotify/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["refreshed"] is False
    assert body["reason"] == "no_tokens"


def test_spotify_refresh_maps_helper_result(monkeypatch, client):
    client.cookies.clear()
    user_id = "refresh-map"
    login = client.post("/v1/auth/login", params={"username": user_id})
    assert login.status_code == 200

    async def fake_refresh(uid: str, store=None) -> str:
        assert uid == user_id
        return "invalid_refresh"

    monkeypatch.setattr(
        "app.api.spotify.refresh_spotify_tokens_for_user", fake_refresh, raising=True
    )

    resp = client.post("/v1/spotify/refresh")
    body = resp.json()
    assert body["refreshed"] is False
    assert body["reason"] == "invalid_refresh_token"  # Should keep distinct from unknown_error


def test_spotify_refresh_handles_api_error(monkeypatch, client):
    client.cookies.clear()
    login = client.post("/v1/auth/login", params={"username": "refresh-error"})
    assert login.status_code == 200

    async def fake_refresh(uid: str) -> str:
        raise SpotifyApiError("network", code="timeout")

    monkeypatch.setattr(
        "app.api.spotify.refresh_spotify_tokens_for_user", fake_refresh, raising=True
    )

    resp = client.post("/v1/spotify/refresh")
    body = resp.json()
    assert body["refreshed"] is False
    assert body["reason"] == "spotify_api_down"
    assert body.get("details", {}).get("code") == "timeout"


@pytest.mark.asyncio
async def test_refresh_spotify_tokens_for_user_success(monkeypatch):
    store: dict[str, ThirdPartyToken] = {}

    async def fake_get_token(user_id: str, provider: str, provider_sub: str | None = None):
        return store.get(user_id)

    async def fake_upsert_token(token: ThirdPartyToken):
        store[token.user_id] = token
        return True

    async def fake_refresh(self, refresh_token: str):
        return {
            "access_token": "new_access_token_value",
            "refresh_token": refresh_token,
            "expires_at": int(time.time()) + 3600,
            "scope": "user-read-currently-playing",
        }

    monkeypatch.setattr("app.auth_store_tokens.get_token", fake_get_token, raising=True)
    monkeypatch.setattr("app.auth_store_tokens.upsert_token", fake_upsert_token, raising=True)
    monkeypatch.setattr(
        "app.integrations.spotify.oauth.SpotifyOAuth.refresh_access_token",
        fake_refresh,
        raising=True,
    )

    user_id = "refresh-helper-success"
    store[user_id] = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        access_token="prev_access_token_value_abcdef",
        refresh_token="refresh_token_success_abcdef",
        scopes="user-read-currently-playing",
        expires_at=int(time.time()) + 3600,
        provider_iss="https://accounts.spotify.com",
        identity_id="spotify-id-success",
        provider_sub="spotify-user-success",
    )

    outcome = await refresh_spotify_tokens_for_user(user_id)
    assert outcome == "ok"
    assert store[user_id].access_token == "new_access_token_value"
    assert store[user_id].last_refresh_at > 0


@pytest.mark.asyncio
async def test_refresh_spotify_tokens_for_user_invalid(monkeypatch):
    from app.integrations.spotify.oauth import SpotifyOAuthError

    store: dict[str, ThirdPartyToken] = {}

    async def fake_get_token(user_id: str, provider: str, provider_sub: str | None = None):
        return store.get(user_id)

    async def fake_upsert_token(token: ThirdPartyToken):
        store[token.user_id] = token
        return True

    async def fake_refresh(self, refresh_token: str):
        raise SpotifyOAuthError(
            "Token refresh failed: 400 {\"error\":\"invalid_grant\",\"error_description\":\"Invalid refresh token\"}"
        )

    monkeypatch.setattr("app.auth_store_tokens.get_token", fake_get_token, raising=True)
    monkeypatch.setattr("app.auth_store_tokens.upsert_token", fake_upsert_token, raising=True)
    monkeypatch.setattr(
        "app.integrations.spotify.oauth.SpotifyOAuth.refresh_access_token",
        fake_refresh,
        raising=True,
    )

    user_id = "refresh-helper-invalid"
    store[user_id] = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        access_token="prev_access_token_value_abcdef",
        refresh_token="refresh_token_invalid_abcdef",
        scopes="user-read-playback-state",
        expires_at=int(time.time()) + 3600,
        provider_iss="https://accounts.spotify.com",
        identity_id="spotify-id-invalid",
        provider_sub="spotify-user-invalid",
    )

    outcome = await refresh_spotify_tokens_for_user(user_id)
    assert outcome == "invalid_refresh"


@pytest.mark.asyncio
async def test_refresh_spotify_tokens_for_user_no_tokens():
    outcome = await refresh_spotify_tokens_for_user("missing-user")
    assert outcome == "no_tokens"


@pytest.mark.asyncio
async def test_refresh_spotify_tokens_for_user_unexpected(monkeypatch):
    store: dict[str, ThirdPartyToken] = {}

    async def fake_get_token(user_id: str, provider: str, provider_sub: str | None = None):
        return store.get(user_id)

    async def fake_upsert_token(token: ThirdPartyToken):
        store[token.user_id] = token
        return True

    async def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.auth_store_tokens.get_token", fake_get_token, raising=True)
    monkeypatch.setattr("app.auth_store_tokens.upsert_token", fake_upsert_token, raising=True)
    monkeypatch.setattr(
        "app.integrations.spotify.oauth.SpotifyOAuth.refresh_access_token",
        boom,
        raising=True,
    )

    user_id = "refresh-helper-error"
    store[user_id] = ThirdPartyToken(
        user_id=user_id,
        provider="spotify",
        access_token="prev_access_token_value_abcdef",
        refresh_token="refresh_token_error_abcdef",
        scopes="user-read-playback-state",
        expires_at=int(time.time()) + 3600,
        provider_iss="https://accounts.spotify.com",
        identity_id="spotify-id-error",
        provider_sub="spotify-user-error",
    )

    with pytest.raises(SpotifyApiError):
        await refresh_spotify_tokens_for_user(user_id)
