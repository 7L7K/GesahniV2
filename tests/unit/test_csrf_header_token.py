import asyncio
from types import SimpleNamespace

import pytest
from starlette.responses import Response

from app.auth.service import AuthService
from app.csrf import _csrf_service, _csrf_token_store, issue_csrf_token


def test_issue_csrf_token_sets_header_cookie_and_store():
    response = Response()

    token = issue_csrf_token(response, request=None)

    assert response.headers["X-CSRF-Token"] == token
    cookie_headers = response.headers.getlist("set-cookie")
    assert any(header.startswith("csrf_token=") for header in cookie_headers)
    assert _csrf_service.validate_token(token)
    assert _csrf_token_store.validate_token(token)


def test_issue_csrf_token_invalid_signature_rejected():
    response = Response()
    token = issue_csrf_token(response, request=None)

    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert not _csrf_service.validate_token(tampered)


@pytest.mark.asyncio
async def test_refresh_tokens_emits_csrf_and_no_store(monkeypatch):
    tokens = iter(["csrf-one", "csrf-two"])

    def fake_issue(response: Response, request):
        token = next(tokens)
        response.headers["X-CSRF-Token"] = token
        response.headers.append("set-cookie", f"csrf_token={token}; Path=/; Max-Age=600")
        return token

    async def fake_rotate(user_id, request, response, refresh_token):
        return {"access_token": "new-access", "user_id": user_id}

    monkeypatch.setattr("app.auth.service.issue_csrf_token", fake_issue)
    monkeypatch.setattr("app.auth_refresh.rotate_refresh_token", fake_rotate)
    monkeypatch.setattr("app.deps.user.get_current_user_id", lambda request=None: "user-42")

    for name in (
        "record_auth_operation",
        "record_error_code",
        "record_refresh_latency",
        "refresh_rotation_failed",
        "refresh_rotation_success",
    ):
        monkeypatch.setattr(f"app.metrics_auth.{name}", lambda *a, **k: None)

    request = SimpleNamespace(state=SimpleNamespace())

    response1 = Response()
    result1 = await AuthService.refresh_tokens(request, response1, refresh_token="rt1")
    assert result1["csrf"] == "csrf-one"
    assert response1.headers["Cache-Control"] == "no-store"
    assert response1.headers["X-CSRF-Token"] == "csrf-one"

    async def no_rotate(user_id, request, response, refresh_token):
        return None

    monkeypatch.setattr("app.auth_refresh.rotate_refresh_token", no_rotate)

    response2 = Response()
    result2 = await AuthService.refresh_tokens(request, response2, refresh_token="rt2")
    assert result2["csrf"] == "csrf-two"
    assert response2.headers["Cache-Control"] == "no-store"
    assert response2.headers["X-CSRF-Token"] == "csrf-two"
    assert "etag" not in {k.lower() for k in response2.headers.keys()}
