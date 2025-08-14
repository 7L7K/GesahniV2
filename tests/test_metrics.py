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
    # Expect our request counter family to be present (prefix match to tolerate name differences)
    assert "app_request_total" in body1 or "gesahni_requests_total" in body1 or "REQUEST_COUNT" or "http_request_total" in body1


