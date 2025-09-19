import asyncio
import os
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.auth.endpoints import login as login_endpoint
from app.auth.endpoints import logout as logout_endpoint


@pytest.fixture(autouse=True)
def _restore_env():
    original = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def _make_request(body: bytes) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/auth/login",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    chunks = [body]

    async def receive():
        if chunks:
            return {"type": "http.request", "body": chunks.pop(0), "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_login_sets_no_store_headers(monkeypatch):
    request = _make_request(b'{"username": "demo"}')
    response = Response()

    monkeypatch.setattr(login_endpoint, "get_cookie_config", lambda request: {})
    monkeypatch.setattr(login_endpoint, "get_token_ttls", lambda: (300, 600))
    monkeypatch.setattr(login_endpoint, "_get_or_create_device_id", lambda request, response: "device")
    monkeypatch.setattr(login_endpoint, "make_access", lambda payload, ttl_s: "access-token")
    monkeypatch.setattr(login_endpoint, "_get_refresh_ttl_seconds", lambda: 600)
    monkeypatch.setattr(login_endpoint, "make_refresh", lambda payload, ttl_s: "refresh-token")
    monkeypatch.setattr(login_endpoint, "rotate_session_id", lambda *a, **k: "session")
    monkeypatch.setattr(login_endpoint, "set_all_auth_cookies", lambda *a, **k: None)

    async def fake_allow_refresh(*args, **kwargs):
        return None

    monkeypatch.setattr(login_endpoint, "allow_refresh", fake_allow_refresh, raising=False)

    async def fake_get_user(username):
        return SimpleNamespace(id="user-uuid")

    monkeypatch.setattr(login_endpoint, "get_user_async", fake_get_user)

    class DummyStore:
        async def ensure_user(self, user_id):
            return None

        async def update_login_stats(self, user_id):
            return None

    monkeypatch.setattr(login_endpoint, "user_store", DummyStore())

    result = await login_endpoint.login(request, response)

    assert response.headers["Cache-Control"] == "no-store"
    assert response.status_code == 200
    assert "X-CSRF-Token" in response.headers
    assert result["csrf"] == response.headers["X-CSRF-Token"]


def test_logout_finalizer_sets_clear_site_data(monkeypatch):
    response = Response()

    # Mock the function to return True for clear site data
    monkeypatch.setattr(logout_endpoint, "_clear_site_data_enabled", lambda: True)

    finalized = logout_endpoint._finalize_logout_response(response)

    assert finalized.headers["Cache-Control"] == "no-store"
    assert finalized.headers["Clear-Site-Data"] == '"cookies"'
    assert finalized.status_code == 200
