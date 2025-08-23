import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH_FOR_ASK", "0")
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    monkeypatch.setenv("NOTIFY_TWILIO_SMS", "0")
    yield


def client():
    os.environ.setdefault("PYTEST_CURRENT_TEST", "care_api")
    return TestClient(app)


def test_alert_create_ack_flow():
    c = client()
    r = c.post("/v1/care/alerts", json={"resident_id": "r1", "kind": "help", "severity": "critical"})
    assert r.status_code == 200
    aid = r.json()["id"]
    a2 = c.post(f"/v1/care/alerts/{aid}/ack", json={"by": "cg1"})
    assert a2.status_code == 200
    assert a2.json()["status"] == "acknowledged"


def test_device_heartbeat_status():
    c = client()
    # initial status -> offline
    s0 = c.get("/v1/care/device_status", params={"device_id": "dev1"})
    assert s0.status_code == 200 and s0.json()["online"] is False
    # heartbeat brings it online
    hb = c.post("/v1/care/devices/dev1/heartbeat", json={"device_id": "dev1", "resident_id": "r1", "battery_pct": 50})
    assert hb.status_code == 200
    s1 = c.get("/v1/care/device_status", params={"device_id": "dev1"})
    assert s1.json()["online"] is True


