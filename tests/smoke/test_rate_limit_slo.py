import os
import sys
import time
from statistics import median

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi.testclient import TestClient

from app.main import app


def test_basic_route_latency_budget():
    # Soft SLO: median latency for /v1/me under 200ms on this machine
    c = TestClient(app)
    samples = []
    for _ in range(10):
        t0 = time.perf_counter()
        r = c.get("/v1/me")
        assert r.status_code == 200
        samples.append((time.perf_counter() - t0) * 1000.0)
    assert median(samples) < 200.0
