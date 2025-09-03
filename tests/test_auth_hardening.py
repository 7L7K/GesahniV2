import os
import time
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

import app.auth as auth
from app.main import app


def test_dynamic_attempt_max_runtime(monkeypatch):
    key = "user:dynamic-test"
    now = time.time()
    # set a single failed attempt
    auth._attempts[key] = (1, now)

    monkeypatch.setenv("LOGIN_ATTEMPT_MAX", "1")
    assert auth._attempt_max() == 1
    # now throttled because count == max
    assert auth._throttled(key) is not None

    # increase limit at runtime (no reimport) and ensure throttling no longer applies
    monkeypatch.setenv("LOGIN_ATTEMPT_MAX", "10")
    assert auth._attempt_max() == 10
    assert auth._throttled(key) is None


def test_rbac_ladder_admin_helpers():
    client = TestClient(app)
    # If legacy auth router (with admin endpoints) isn't mounted in this app instance,
    # skip — some test environments disable legacy admin routes via admin_enabled().
    route_exists = any(
        r.path == "/v1/auth/admin/rate-limits/{key}" for r in app.router.routes
    )
    if not route_exists:
        pytest.skip("Legacy auth router not mounted; skipping RBAC ladder test")

    # Helper overrides
    def raise_401(required: str):
        raise HTTPException(status_code=401)

    def raise_403(required: str):
        raise HTTPException(status_code=403)

    # 401 unauth (override the shared require_scope dependency used by routes)
    from app.deps.scopes import require_scope as _require_scope

    app.dependency_overrides[_require_scope] = raise_401
    r = client.get("/v1/auth/admin/rate-limits/user:demo")
    assert r.status_code == 401

    # 403 authenticated but not scoped
    app.dependency_overrides[_require_scope] = raise_403
    r = client.get("/v1/auth/admin/rate-limits/user:demo")
    assert r.status_code == 403

    # admin:read -> GET allowed (may return 200 or 404 if no data)
    app.dependency_overrides[_require_scope] = lambda required: None  # allow
    r = client.get("/v1/auth/admin/rate-limits/user:demo")
    assert r.status_code in (200, 404)

    # admin:write -> DELETE allowed
    r = client.delete("/v1/auth/admin/rate-limits/user:demo")
    assert r.status_code in (200, 204)

    app.dependency_overrides.clear()


def test_rate_limit_throttle_and_window_reset(monkeypatch):
    key = "user:rl-test"
    now = time.time()

    # set small window and a stale timestamp to simulate expiry
    monkeypatch.setenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "1")
    # create an entry older than the window
    auth._attempts[key] = (5, now - 10)
    # since timestamp is old, throttled should return None
    assert auth._throttled(key) is None

    # set recent attempts above max
    monkeypatch.setenv("LOGIN_ATTEMPT_MAX", "3")
    auth._attempts[key] = (4, now)
    assert auth._throttled(key) is not None


def test_backoff_threshold_logic(monkeypatch):
    user_key = "user:backoff"
    # ensure backoff threshold is dynamic
    monkeypatch.setenv("LOGIN_BACKOFF_THRESHOLD", "2")
    auth._attempts[user_key] = (3, time.time())
    assert auth._should_apply_backoff(user_key) is True

    monkeypatch.setenv("LOGIN_BACKOFF_THRESHOLD", "10")
    assert auth._should_apply_backoff(user_key) is False


def test_session_binding_and_verify(monkeypatch):
    # Fake session store
    class FakeStore:
        def __init__(self):
            self._map = {}

        def create_session(self, jti, expires_at):
            sid = f"sess_{jti}"
            self._map[sid] = jti
            return sid

        def get_session(self, session_id):
            return self._map.get(session_id)

        def delete_session(self, session_id):
            return self._map.pop(session_id, None) is not None

    import app.session_store as session_store_mod

    fake = FakeStore()
    monkeypatch.setattr(session_store_mod, "get_session_store", lambda: fake)

    jti = "jti-xyz"
    exp = time.time() + 60
    sid = auth._create_session_id(jti, exp)
    # verify mapping exists
    assert fake.get_session(sid) == jti
    assert auth._verify_session_id(sid, jti) is True

    # cleanup
    assert auth._delete_session_id(sid) is True


# The following tests require full endpoint integration (CSRF, asyncio sleep assertions)
# and are left as placeholders that can be enabled in an environment that runs the
# full application stack.


@pytest.mark.skip(
    reason="Requires full server CSRF + cookie setup; run in integration suite"
)
def test_csrf_enforcement_on_login():
    pass


@pytest.mark.skip(reason="Integration test: exercise login endpoint backoff sleep")
def test_backoff_sleep_in_login():
    pass
