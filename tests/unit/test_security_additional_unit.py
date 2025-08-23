import os
from pathlib import Path

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request


def _auth_header(uid: str = "u", scopes: str | None = None) -> dict:
    payload: dict = {"user_id": uid}
    if scopes:
        payload["scope"] = scopes
    token = jwt.encode(payload, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_get_rate_limit_defaults_keys():
    import app.security as sec

    d = sec.get_rate_limit_defaults()
    assert set(["limit", "burst_limit", "window_s", "burst_window_s"]).issubset(
        d.keys()
    )


def test_bucket_rate_limit_counts_and_limit():
    import app.security as sec

    b = {}
    assert sec._bucket_rate_limit("k", b, 2, 60.0)
    assert sec._bucket_rate_limit("k", b, 2, 60.0)
    assert not sec._bucket_rate_limit("k", b, 2, 60.0)


def test_bucket_retry_after_non_negative():
    import app.security as sec

    b = {}
    assert sec._bucket_retry_after(b, 1.0) >= 0


def test_get_request_payload_from_header():
    import app.security as sec

    tok = jwt.encode(
        {"user_id": "u1", "scope": "admin"},
        os.getenv("JWT_SECRET", "secret"),
        algorithm="HS256",
    )
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"authorization", f"Bearer {tok}".encode())],
    }
    req = Request(scope)
    # Private helper is accessible
    p = sec._get_request_payload(req)
    assert isinstance(p, dict) and (p.get("user_id") == "u1")


def test_bypass_scopes_env_parsing(monkeypatch):
    import app.security as sec

    monkeypatch.setenv("RATE_LIMIT_BYPASS_SCOPES", "admin support")
    s = sec._bypass_scopes_env()
    assert "admin" in s and "support" in s


@pytest.mark.asyncio
async def test_daily_incr_local_counter(monkeypatch):
    import app.security as sec

    c1, ttl1 = await sec._daily_incr(None, "u1")
    c2, ttl2 = await sec._daily_incr(None, "u1")
    assert c1 == 1 and c2 == 2
    assert ttl1 >= 0 and ttl2 >= 0


def test_rl_key_format():
    import app.security as sec

    k = sec._rl_key("http", "user", "long")
    assert k.startswith("rl:http:user:") and k.endswith("long")


@pytest.mark.asyncio
async def test_require_nonce_disabled_passes(monkeypatch):
    import app.security as sec

    monkeypatch.setenv("REQUIRE_NONCE", "0")
    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    await sec.require_nonce(req)


@pytest.mark.asyncio
async def test_verify_webhook_missing_secret(monkeypatch):
    from fastapi import HTTPException

    import app.security as sec

    monkeypatch.delenv("HA_WEBHOOK_SECRETS", raising=False)
    monkeypatch.delenv("HA_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv(
        "HA_WEBHOOK_SECRET_FILE", str(Path("/tmp/nonexistent_secret.txt"))
    )
    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []})

    async def _set_body():
        return b"{}"

    # Patch body method to return bytes
    req.body = _set_body  # type: ignore
    with pytest.raises(HTTPException) as e:
        await sec.verify_webhook(req)
    assert e.value.status_code == 500


def test_rotate_webhook_secret_writes_file(tmp_path: Path, monkeypatch):
    import app.security as sec

    path = tmp_path / "secret.txt"
    monkeypatch.setenv("HA_WEBHOOK_SECRET_FILE", str(path))
    new = sec.rotate_webhook_secret()
    assert isinstance(new, str) and len(new) >= 16
    assert path.exists() and new in path.read_text()


def test_middleware_sets_rate_limit_headers_on_healthz():
    from app.main import app

    c = TestClient(app)
    r = c.get("/v1/healthz")
    assert r.status_code == 200
    # Headers should be present even if counts are zero
    assert "RateLimit-Limit" in r.headers
    assert "RateLimit-Remaining" in r.headers


@pytest.mark.asyncio
async def test_rate_limit_backend_status_helper(monkeypatch):
    import app.security as sec

    # Force memory mode
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    data = await sec.get_rate_limit_backend_status()
    assert data.get("backend") in ("memory", "redis")
    assert "limits" in data and "windows_s" in data


def _app_with_rate_limit():
    import app.security as sec

    app = FastAPI()

    @app.get("/ping", dependencies=[Depends(sec.rate_limit)])
    async def ping():
        return {"ok": True}

    return app


def test_rate_limit_http_burst_block_when_limit_one(monkeypatch):
    # Configure burst=1 and long high by patching module constants (import-time)
    import app.security as sec

    monkeypatch.setattr(sec, "RATE_LIMIT_BURST", 1)
    monkeypatch.setattr(sec, "RATE_LIMIT", 1000)
    c = TestClient(_app_with_rate_limit())
    h = _auth_header("u_burst")
    assert c.get("/ping", headers=h).status_code == 200
    r2 = c.get("/ping", headers=h)
    assert r2.status_code == 429
    assert r2.headers.get("Retry-After") is not None


def test_rate_limit_http_long_block_when_limit_one(monkeypatch):
    # Configure long=1 and burst high by patching module constants
    import app.security as sec

    monkeypatch.setattr(sec, "RATE_LIMIT", 1)
    monkeypatch.setattr(sec, "RATE_LIMIT_BURST", 100)
    c = TestClient(_app_with_rate_limit())
    h = _auth_header("u_long")
    assert c.get("/ping", headers=h).status_code == 200
    assert c.get("/ping", headers=h).status_code == 429


def test_scope_rate_limit_no_scope_delegates_to_default(monkeypatch):
    import app.security as sec

    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1000")
    app = FastAPI()

    @app.get(
        "/admin",
        dependencies=[
            Depends(sec.scope_rate_limit("admin", long_limit=1, burst_limit=1))
        ],
    )
    async def admin():
        return {"ok": True}

    c = TestClient(app)
    h = _auth_header("u_scope")  # no admin scope
    for _ in range(3):
        assert c.get("/admin", headers=h).status_code == 200
