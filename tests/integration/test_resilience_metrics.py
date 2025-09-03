import re
from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app

METRICS_ENDPOINT = "/metrics"


def _get_metrics_text(client):
    r = client.get(METRICS_ENDPOINT)
    assert r.status_code == HTTPStatus.OK
    return r.text


def test_metrics_exist_after_forced_errors(monkeypatch):
    client = TestClient(app)
    # Ensure test helpers are enabled
    monkeypatch.setenv("PROMETHEUS_ENABLED", "1")

    # Force 429 on an idempotent GET: use an existing limiter-aware endpoint
    # We may not have a dedicated test endpoint; call /v1/state repeatedly to trigger burst/long limit in tests.
    client.get("/v1/state")
    client.get("/v1/state")
    client.get("/v1/state")

    # Force SSE failure: call ask with a short timeout (stream aborted)
    try:
        client.post("/v1/ask", json={"prompt": "hi"}, timeout=0.001)
    except Exception:
        pass

    metrics = _get_metrics_text(client)
    for name in [
        "ws_reconnect_total",
        "ws_time_to_reconnect_seconds",
        "sse_fail_total",
        "sse_partial_stream_total",
        "sse_retry_total",
        "api_retry_total",
        "api_retry_success_ratio",
    ]:
        # Use doubled braces in f-string to match literal braces in regex
        assert re.search(rf"^{name}(\{{.*\}})?\s", metrics, re.M) or (
            name in metrics
        ), f"metric {name} not exported"
