import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi.testclient import TestClient

from app.main import app


def test_rate_limit_headers_present():
    c = TestClient(app)
    r = c.get("/v1/me")
    assert r.status_code == 200
    # Presence only; values vary by environment
    assert "RateLimit-Limit" in r.headers
    assert "RateLimit-Remaining" in r.headers
    assert "RateLimit-Reset" in r.headers
