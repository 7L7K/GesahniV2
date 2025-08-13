from fastapi.testclient import TestClient


def test_rate_limit_status_contains_prefix_and_windows():
    from app.main import app

    c = TestClient(app)
    r = c.get("/v1/rate_limit_status")
    assert r.status_code == 200
    data = r.json()
    assert "prefix" in data
    assert "windows_s" in data and "long" in data["windows_s"]


