import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_sessions_returns_empty_on_store_failure(monkeypatch, client):
    from app.api import me as me_module

    async def _fail_list(user_id: str):
        raise RuntimeError("db down")

    async def _user_dep():
        return "user-123"

    monkeypatch.setattr(me_module.sessions_store, "list_user_sessions", _fail_list)
    app.dependency_overrides[me_module.get_current_user_id] = _user_dep
    try:
        resp = client.get("/v1/sessions")
    finally:
        app.dependency_overrides.pop(me_module.get_current_user_id, None)

    assert resp.status_code == 200
    assert resp.json() == []


def test_google_status_handles_store_failure(monkeypatch, client):
    import app.auth_store_tokens as tokens_mod
    from app.api import google as google_module

    async def _user_dep():
        return "user-123"

    async def _fail_token(user_id: str, provider: str):
        raise RuntimeError("db down")

    app.dependency_overrides[google_module.get_current_user_id] = _user_dep
    monkeypatch.setattr(
        tokens_mod,
        "get_token_by_user_identities",
        _fail_token,
        raising=True,
    )
    try:
        resp = client.get("/v1/integrations/google/status")
    finally:
        app.dependency_overrides.pop(google_module.get_current_user_id, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["degraded_reason"] == "unavailable"


def test_health_google_available(client):
    resp = client.get("/v1/health/google")
    assert resp.status_code == 200
    assert resp.json().get("service") == "google"


def test_pats_get_requires_auth(client):
    resp = client.get("/v1/pats")
    assert resp.status_code == 401
