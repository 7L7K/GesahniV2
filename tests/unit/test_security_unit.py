import types

import pytest
from fastapi import HTTPException


def test_get_rate_limit_snapshot_and_current_key(monkeypatch):
    from app import security as sec

    # reset buckets
    sec._http_requests.clear()
    sec.http_burst.clear()

    class DummyReq:
        def __init__(self):
            self.state = types.SimpleNamespace(user_id="u1", jwt_payload=None)
            self.headers = {}
            self.client = types.SimpleNamespace(host="h")

    req = DummyReq()
    # pre-populate some counts
    sec._http_requests["u1"] = 3
    sec.http_burst["u1"] = 1
    snap = sec.get_rate_limit_snapshot(req)
    assert set(
        ["limit", "remaining", "reset", "burst_limit", "burst_remaining", "burst_reset"]
    ).issubset(snap.keys())


@pytest.mark.asyncio
async def test_verify_token_missing_secret(monkeypatch):
    from fastapi import Request

    from app import security as sec

    # Missing secret but REQUIRE_JWT disabled -> pass-through
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("REQUIRE_JWT", "0")

    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    req = Request(scope)
    await sec.verify_token(req)


@pytest.mark.asyncio
async def test_verify_token_success(monkeypatch):
    from fastapi import Request

    from app import security as sec

    monkeypatch.setenv("JWT_SECRET", "secret")
    from app.tokens import create_access_token

    token = create_access_token({"user_id": "u2"})
    headers = [(b"authorization", f"Bearer {token}".encode())]
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers}
    req = Request(scope)
    await sec.verify_token(req)
    assert getattr(req.state, "jwt_payload", {}).get("user_id") == "u2"


@pytest.mark.asyncio
async def test_rate_limit_paths(monkeypatch):
    from fastapi import Request

    from app import security as sec

    # allow more burst to avoid flakiness
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    monkeypatch.setenv("RATE_LIMIT_BURST", "5")

    sec._http_requests.clear()
    sec.http_burst.clear()

    from app.tokens import create_access_token

    token = create_access_token({"user_id": "u2"})
    headers = [(b"authorization", f"Bearer {token}".encode())]
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers}
    req = Request(scope)
    # attach payload as if verify_token ran
    req.state.jwt_payload = {"user_id": "u2"}

    # first N within burst/long windows are OK; we call the function directly
    for _ in range(5):
        await sec.rate_limit(req)


@pytest.mark.asyncio
async def test_require_nonce(monkeypatch):
    from fastapi import Request

    from app import security as sec

    monkeypatch.setenv("REQUIRE_NONCE", "1")
    monkeypatch.setenv("NONCE_TTL_SECONDS", "1")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"x-nonce", b"n1")],
    }
    req = Request(scope)
    await sec.require_nonce(req)

    # reuse -> conflict
    with pytest.raises(HTTPException):
        await sec.require_nonce(req)
