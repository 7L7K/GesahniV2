import asyncio
import time
from fastapi.testclient import TestClient

from app.main import app
import app.health_utils as hu


def test_health_ready_ok(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test")

    async def ok_db():
        return "ok"

    monkeypatch.setattr(hu, "check_db", ok_db)
    c = TestClient(app)
    r = c.get("/healthz/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ready_db_fail(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test")

    async def bad_db():
        return "error"

    monkeypatch.setattr(hu, "check_db", bad_db)
    c = TestClient(app)
    r = c.get("/healthz/ready")
    assert r.status_code == 503
    body = r.json()
    assert body.get("status") == "fail"
    assert "db" in set(body.get("failing") or [])


def test_health_ready_timeout_enforced(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test")

    async def hang_db():
        await asyncio.sleep(2)
        return "ok"

    monkeypatch.setattr(hu, "check_db", hang_db)
    c = TestClient(app)
    t0 = time.time()
    r = c.get("/healthz/ready")
    # Should return quickly despite hang (under ~0.8s to be safe)
    assert (time.time() - t0) < 0.8
    assert r.status_code == 503


