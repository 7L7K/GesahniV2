from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_status_reports_quiet_hours(monkeypatch):
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("QUIET_HOURS", "1")
    monkeypatch.setenv("QUIET_HOURS_START", "00:00")
    monkeypatch.setenv("QUIET_HOURS_END", "23:59")
    client = TestClient(app)
    res = client.get("/v1/status")
    assert res.status_code == 200
    data = res.json()
    assert data.get("quiet_hours", {}).get("enabled") is True
    assert data.get("quiet_hours", {}).get("active") in {True, False}


