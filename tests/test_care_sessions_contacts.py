import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from app.main import app


def client():
    return TestClient(app)


def test_sessions_crud(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    c = client()
    sid = uuid.uuid4().hex
    r = c.post("/v1/care/sessions", json={"id": sid, "resident_id": "r1", "title": "Daily call"})
    assert r.status_code == 200
    r2 = c.patch(f"/v1/care/sessions/{sid}", json={"transcript_uri": "s3://bucket/file.txt"})
    assert r2.status_code == 200
    r3 = c.get("/v1/care/sessions")
    assert r3.status_code == 200 and any(x["id"] == sid for x in r3.json().get("items", []))


