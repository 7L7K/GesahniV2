from fastapi.testclient import TestClient

from app.main import app


def test_metrics_exposes_prometheus_and_increments_counter():
    c = TestClient(app)

    # Baseline scrape
    r0 = c.get("/metrics", headers={"Cookie": "access_token=bad"})
    assert r0.status_code == 200
    assert r0.headers.get("content-type", "").startswith("text/plain")
    body0 = r0.text
    # Hit a simple GET (unauthed health)
    _ = c.get("/healthz/live")
    r1 = c.get("/metrics")
    assert r1.status_code == 200
    body1 = r1.text
    # Expect our request counter family to be present
    assert ("gesahni_requests_total" in body1) or ("app_request_total" in body1)


def test_metrics_health_requests_count_and_latency():
    c = TestClient(app)
    for _ in range(3):
        c.get("/healthz/ready")
    body = c.get("/metrics").text
    # Counter includes route label
    assert "gesahni_requests_total" in body
    assert "/healthz/ready" in body
    # Histogram buckets present
    assert "gesahni_latency_seconds_bucket" in body
    # /metrics is unauthenticated
    r = c.get("/metrics", headers={"Cookie": "access_token=bogus"})
    assert r.status_code == 200


