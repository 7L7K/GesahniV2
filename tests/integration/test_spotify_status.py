from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.deps.user import get_current_user_id
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class Tok(SimpleNamespace):
    pass


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
    yield


def test_status_connected_false_when_invalid_or_expired(client, monkeypatch):
    # Mock the get_current_user_id dependency
    def mock_get_current_user_id():
        return "test-user-id"

    client.app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

    async def fake_get_token(
        uid, provider
    ):  # used by your status impl if it queries store
        return Tok(
            is_valid=False,
            expires_at=9999999999,
            scope="user-read-email user-read-private",
        )

    monkeypatch.setattr("app.api.spotify.get_token", fake_get_token, raising=False)

    try:
        r = client.get("/v1/integrations/spotify/status")
        assert r.status_code == 200
        body = r.json()
        assert body["connected"] is False
    finally:
        client.app.dependency_overrides.pop(get_current_user_id, None)


def test_status_connected_true_when_valid_token(client, monkeypatch):
    # Mock the get_current_user_id dependency
    def mock_get_current_user_id():
        return "test-user-id"

    client.app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

    # Mock the database call to return a valid token
    async def fake_get_token(user_id, provider):
        return Tok(
            is_valid=True,
            expires_at=9999999999,
            scopes="user-read-email user-read-private",
        )

    monkeypatch.setattr("app.auth_store_tokens.get_token", fake_get_token)

    try:
        r = client.get("/v1/integrations/spotify/status")
        assert r.status_code == 200
        body = r.json()
        assert body["connected"] is True
        assert body["scopes"] == ["user-read-email", "user-read-private"]
    finally:
        client.app.dependency_overrides.pop(get_current_user_id, None)


def test_accept_header_json_branch(client, monkeypatch):
    # ensure JSON branch triggers for compound Accept header
    r = client.get(
        "/v1/spotify/callback?code=abc",
        headers={"Accept": "application/json, text/plain, */*"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "missing_state"
