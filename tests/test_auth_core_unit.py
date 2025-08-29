import os

import jwt

from app.auth_core import extract_token, decode_any, resolve_auth
from app.auth_core import has_scope, require_scope


class FakeTarget:
    def __init__(self, headers=None, cookies=None):
        class _State:
            pass

        self.state = _State()
        self.headers = headers or {}
        self.cookies = cookies or {}


def test_extract_token_precedence_header_over_cookie():
    t = FakeTarget(headers={"Authorization": "Bearer abc"}, cookies={"GSNH_AT": "cookie"})
    src, tok = extract_token(t)
    assert src == "authorization"
    assert tok == "abc"


def test_extract_token_access_cookie_when_no_header():
    t = FakeTarget(headers={}, cookies={"GSNH_AT": "cookie"})
    src, tok = extract_token(t)
    assert src == "access_cookie"
    assert tok == "cookie"


def test_extract_token_session_when_no_header_or_access():
    t = FakeTarget(headers={}, cookies={"GSNH_SESS": "sess_123"})
    src, tok = extract_token(t)
    assert src == "session"
    assert tok == "sess_123"


def test_decode_any_hs256_roundtrip(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-secret")
    token = jwt.encode({"sub": "u1"}, "unit-secret", algorithm="HS256")
    payload = decode_any(token)
    assert payload.get("sub") == "u1"


def test_resolve_auth_sets_state_for_access_cookie(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-secret")
    tok = jwt.encode({"user_id": "alice"}, "unit-secret", algorithm="HS256")
    t = FakeTarget(headers={}, cookies={"GSNH_AT": tok})
    out = resolve_auth(t)
    assert out["user_id"] == "alice"
    assert getattr(t.state, "user_id", None) == "alice"


def test_has_scope_and_require_scope(monkeypatch):
    payload = {"scopes": ["music:control", "care:resident"]}
    assert has_scope(payload, "music:control") is True
    assert has_scope(payload, "admin:write") is False

