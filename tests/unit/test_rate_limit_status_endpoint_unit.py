from fastapi.testclient import TestClient

from app.main import app


def test_rate_limit_status_endpoint_defaults():
    client = TestClient(app)
    r = client.get("/v1/rate_limit_status")
    assert r.status_code == 200
    data = r.json()
    assert "backend" in data
    assert data["backend"] in ("memory", "redis")
    assert "limits" in data and "windows_s" in data
