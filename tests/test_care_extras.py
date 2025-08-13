import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    # isolate care DB per test run
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "care_extras")
    yield


def client():
    return TestClient(app)


def test_alert_validation_invalid_kind():
    c = client()
    r = c.post("/v1/care/alerts", json={"resident_id": "r1", "kind": "bad", "severity": "info"})
    assert r.status_code == 400


def test_alert_validation_invalid_severity():
    c = client()
    r = c.post("/v1/care/alerts", json={"resident_id": "r1", "kind": "help", "severity": "nope"})
    assert r.status_code == 400


def test_alert_ack_idempotent():
    c = client()
    r = c.post("/v1/care/alerts", json={"resident_id": "r1", "kind": "help", "severity": "critical"})
    aid = r.json()["id"]
    a1 = c.post(f"/v1/care/alerts/{aid}/ack", json={"by": "cg1"})
    assert a1.json()["status"] == "acknowledged"
    a2 = c.post(f"/v1/care/alerts/{aid}/ack", json={"by": "cg2"})
    assert a2.json()["status"] == "acknowledged"


def test_alert_resolve_flow():
    c = client()
    r = c.post("/v1/care/alerts", json={"resident_id": "r2", "kind": "help", "severity": "warn"})
    aid = r.json()["id"]
    rr = c.post(f"/v1/care/alerts/{aid}/resolve")
    body = rr.json()
    assert body["status"] == "resolved" and body.get("resolved_at") is not None


def test_alert_list_filter_by_resident():
    c = client()
    c.post("/v1/care/alerts", json={"resident_id": "alice", "kind": "help", "severity": "info"})
    c.post("/v1/care/alerts", json={"resident_id": "bob", "kind": "help", "severity": "info"})
    ra = c.get("/v1/care/alerts", params={"resident_id": "alice"})
    items = ra.json().get("items", [])
    assert all(it["resident_id"] == "alice" for it in items)


def test_alert_sms_enqueued(monkeypatch):
    # Force SMS path and capture queue push
    pushed = {}

    class Q:
        async def push(self, payload):
            pushed.update(payload)

    import app.queue as aq

    monkeypatch.setenv("NOTIFY_TWILIO_SMS", "1")
    monkeypatch.setattr(aq, "get_queue", lambda name: Q())
    c = client()
    c.post("/v1/care/alerts", json={"resident_id": "r1", "kind": "help", "severity": "critical"})
    assert pushed.get("body", "").startswith("Alert:")


def test_ws_broadcast_created_and_ack():
    c = client()
    with c.websocket_connect("/v1/ws/care") as ws:
        ws.send_json({"action": "subscribe", "topic": "resident:r1"})
        r = c.post("/v1/care/alerts", json={"resident_id": "r1", "kind": "help", "severity": "critical"})
        evt = ws.receive_json()
        assert evt.get("data", {}).get("event") == "alert.created" or evt.get("data", {}).get("kind") == "help"
        aid = r.json()["id"]
        c.post(f"/v1/care/alerts/{aid}/ack", json={"by": "cg1"})
        evt2 = ws.receive_json()
        # either event wrapper or flattened {event: 'alert.acknowledged'}
        assert "ack" in (evt2.get("data", {}).get("event") or str(evt2))


def test_heartbeat_online_and_offline_by_time(monkeypatch):
    import app.api.care as care_api

    c = client()
    # heartbeat brings online
    c.post("/v1/care/devices/devX/heartbeat", json={"device_id": "devX", "resident_id": "r1"})
    s1 = c.get("/v1/care/device_status", params={"device_id": "devX"})
    assert s1.json()["online"] is True
    # Simulate time jump > 90s
    base_now = care_api._now()
    monkeypatch.setattr(care_api, "_now", lambda: base_now + 120)
    s2 = c.get("/v1/care/device_status", params={"device_id": "devX"})
    assert s2.json()["online"] is False


def test_device_battery_in_status():
    c = client()
    c.post("/v1/care/devices/devY/heartbeat", json={"device_id": "devY", "resident_id": "r1", "battery_pct": 11})
    s = c.get("/v1/care/device_status", params={"device_id": "devY"})
    assert s.json().get("battery") == 11


def test_sessions_filter_by_resident(monkeypatch):
    c = client()
    sid1 = uuid.uuid4().hex
    sid2 = uuid.uuid4().hex
    c.post("/v1/care/sessions", json={"id": sid1, "resident_id": "a", "title": "T1"})
    c.post("/v1/care/sessions", json={"id": sid2, "resident_id": "b", "title": "T2"})
    r = c.get("/v1/care/sessions", params={"resident_id": "b"})
    assert all(it["resident_id"] == "b" for it in r.json().get("items", []))


def test_contacts_crud_create_list_update_delete():
    c = client()
    r = c.post(
        "/v1/care/contacts",
        json={"resident_id": "r1", "name": "Leola", "phone": "+15551234567", "priority": 10},
    )
    cid = r.json()["id"]
    l = c.get("/v1/care/contacts", params={"resident_id": "r1"})
    assert any(it["id"] == cid for it in l.json().get("items", []))
    u = c.patch(f"/v1/care/contacts/{cid}", json={"priority": 5, "quiet_hours": {"start": "22:00", "end": "06:00"}})
    assert u.status_code == 200
    l2 = c.get("/v1/care/contacts", params={"resident_id": "r1"}).json()["items"]
    found = [it for it in l2 if it["id"] == cid][0]
    assert found["priority"] == 5 and isinstance(found.get("quiet_hours"), dict)
    d = c.delete(f"/v1/care/contacts/{cid}")
    assert d.status_code == 200


def test_ack_via_link_token_flow():
    c = client()
    r = c.post("/v1/care/alerts", json={"resident_id": "r1", "kind": "help", "severity": "critical"})
    aid = r.json()["id"]
    tok = c.get("/v1/care/ack_token", params={"alert_id": aid, "ttl_seconds": 60}).json()["token"]
    a2 = c.post("/v1/care/alerts/ack_via_link", params={"token": tok})
    assert a2.json()["status"] == "acknowledged"


def test_contacts_quiet_hours_json_handling():
    c = client()
    r = c.post(
        "/v1/care/contacts",
        json={"resident_id": "r2", "name": "Jamal", "phone": None, "priority": 1},
    )
    cid = r.json()["id"]
    c.patch(f"/v1/care/contacts/{cid}", json={"quiet_hours": {"days": ["sat", "sun"]}})
    items = c.get("/v1/care/contacts", params={"resident_id": "r2"}).json()["items"]
    qh = [it for it in items if it["id"] == cid][0]["quiet_hours"]
    assert qh.get("days") == ["sat", "sun"]


def test_alert_resolve_nonexistent():
    c = client()
    rr = c.post("/v1/care/alerts/does-not-exist/resolve")
    assert rr.status_code == 404


def test_ack_invalid_token():
    c = client()
    bad = "invalid-token"
    a = c.post("/v1/care/alerts/ack_via_link", params={"token": bad})
    assert a.status_code == 400


