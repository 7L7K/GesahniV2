import secrets
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_startup_requires_strong_secret():
    """If JWT_SECRET is missing or weak, startup checks should fail fast with a clear message."""
    from app.secret_verification import log_secret_summary

    # Ensure absence of JWT_SECRET triggers the RuntimeError used during startup
    with pytest.raises(RuntimeError) as exc:
        with pytest.MonkeyPatch.context() as m:
            m.delenv("JWT_SECRET", raising=False)
            log_secret_summary()

    assert str(exc.value) == "JWT_SECRET too weak (need >=32 bytes)"


def test_cookie_names_canonical_only():
    """Login flow must return only canonical GSNH_* cookie names (no legacy names)."""
    # Provide a strong secret so the app can mint tokens
    strong = secrets.token_hex(32)
    with pytest.MonkeyPatch.context() as m:
        m.setenv("JWT_SECRET", strong)
        client = TestClient(app)

        # Call dev login endpoint (simple username-based login)
        r = client.post("/v1/auth/login?username=testuser")
        assert r.status_code == 200

        # Inspect cookie jar on the TestClient session
        cookie_names = {c.name for c in client.cookies.jar}

        # Canonical names expected
        assert "GSNH_AT" in cookie_names
        assert "GSNH_RT" in cookie_names
        assert "GSNH_SESS" in cookie_names

        # Legacy names must NOT be present
        assert "access_token" not in cookie_names
        assert "refresh_token" not in cookie_names
        assert "__session" not in cookie_names


def test_jwt_leeway_60s():
    """JWT decode should accept nbf up to 60s in the future and reject beyond that."""
    secret = "s" * 64
    now = int(time.time())

    # nbf 30s in future -> should be accepted with leeway=60
    payload_ok = {"user_id": "u", "iat": now, "nbf": now + 30, "exp": now + 3600}
    token_ok = jwt.encode(payload_ok, secret, algorithm="HS256")
    decoded = jwt.decode(token_ok, secret, algorithms=["HS256"], leeway=60)
    assert decoded.get("user_id") == "u"

    # nbf 120s in future -> should fail with leeway=60
    payload_bad = {"user_id": "u", "iat": now, "nbf": now + 120, "exp": now + 3600}
    token_bad = jwt.encode(payload_bad, secret, algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token_bad, secret, algorithms=["HS256"], leeway=60)


