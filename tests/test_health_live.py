import time
from fastapi.testclient import TestClient

from app.main import app


def test_health_live_basic_ok():
    c = TestClient(app)
    t0 = time.time()
    r = c.get("/healthz/live", headers={"Cookie": "access_token=bad"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    # Responds quickly (within 1s on CI; typically <100ms)
    assert (time.time() - t0) < 1.0


def test_health_live_no_auth_required():
    c = TestClient(app)
    r = c.get("/healthz/live")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_health_live_cache_headers_and_no_cookies():
    c = TestClient(app)
    r = c.get("/healthz/live", headers={"Cookie": "access_token=bogus"})
    assert r.status_code == 200
    # no-store cache hint
    assert r.headers.get("Cache-Control") == "no-store"
    assert r.headers.get("Pragma") == "no-cache"
    # should not set any cookies for probes
    assert "set-cookie" not in {k.lower() for k in r.headers.keys()}


def test_health_live_not_rate_limited_under_hammer():
    c = TestClient(app)
    codes = [c.get("/healthz/live").status_code for _ in range(20)]
    assert all(code == 200 for code in codes)


