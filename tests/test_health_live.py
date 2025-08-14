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


