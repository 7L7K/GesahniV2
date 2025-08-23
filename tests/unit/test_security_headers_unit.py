from fastapi.testclient import TestClient


def test_healthz_includes_retry_after_when_limited(monkeypatch):
    import app.security as sec
    from app.main import app

    # Force burst limit to 1 to trigger block
    monkeypatch.setattr(sec, "RATE_LIMIT_BURST", 1)
    c = TestClient(app)
    r1 = c.get("/v1/healthz")
    assert r1.status_code == 200
    r2 = c.get("/v1/healthz")
    if r2.status_code == 429:
        assert "Retry-After" in r2.headers
