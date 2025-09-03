import asyncio
import time

from fastapi.testclient import TestClient

import app.health_utils as hu
from app.main import app


def test_health_ready_ok(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET",
        "test_jwt_secret_that_is_long_enough_for_validation_purposes_123456789",
    )

    async def ok_db():
        return "ok"

    monkeypatch.setattr(hu, "check_db", ok_db)
    c = TestClient(app)
    r = c.get("/healthz/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ok"] is True
    assert "components" in body
    assert body["components"]["jwt_secret"]["status"] == "healthy"
    assert body["components"]["db"]["status"] == "healthy"


def test_health_ready_db_fail(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET",
        "test_jwt_secret_that_is_long_enough_for_validation_purposes_123456789",
    )

    async def bad_db():
        return "error"

    monkeypatch.setattr(hu, "check_db", bad_db)
    c = TestClient(app)
    r = c.get("/healthz/ready")
    assert r.status_code == 200  # Readiness probes never return 5xx
    body = r.json()
    assert body.get("status") == "unhealthy"
    assert "db" in set(body.get("failing") or [])


def test_health_ready_timeout_enforced(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET",
        "test_jwt_secret_that_is_long_enough_for_validation_purposes_123456789",
    )

    async def hang_db():
        await asyncio.sleep(2)
        return "ok"

    monkeypatch.setattr(hu, "check_db", hang_db)
    c = TestClient(app)
    t0 = time.time()
    r = c.get("/healthz/ready")
    # Should return quickly despite hang (under ~0.8s to be safe)
    assert (time.time() - t0) < 0.8
    assert r.status_code == 200  # Readiness probes never return 5xx
    body = r.json()
    assert body["status"] == "unhealthy"
    assert body["ok"] is False
    assert "db" in body.get("failing", [])
