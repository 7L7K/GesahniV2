import time

from fastapi.testclient import TestClient

from app.main import app


def test_rate_limit_smoke_csrf_endpoint(monkeypatch):
    """Smoke test: Hit /v1/csrf > N times quickly, last call should return 429."""

    # Temporarily disable pytest detection to enable rate limiting
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_RUNNING", raising=False)

    # Import the rate limiting helpers
    from app.middleware.rate_limit import (
        _test_clear_buckets,
        _test_clear_metrics,
        _test_set_config,
    )

    # Clear any existing rate limit state and metrics
    _test_clear_buckets()
    _test_clear_metrics()

    # Configure a very low rate limit for this test (5 requests per minute)
    # This makes the test fast and reliable
    _test_set_config(max_req=5, window_s=60)

    # Get initial metrics
    from app.middleware.rate_limit import get_metrics

    initial_metrics = get_metrics()

    # Make more than 5 requests quickly to trigger rate limiting
    requests_made = 0
    last_response = None

    with TestClient(app) as client:
        for i in range(7):  # Make 7 requests (more than our limit of 5)
            response = client.get("/v1/csrf")
            requests_made += 1
            last_response = response

            # If we hit the rate limit, break early
            if response.status_code == 429:
                break

            # Small delay to ensure requests are processed
            time.sleep(0.01)

    # Verify we made more requests than the limit
    assert (
        requests_made > 5
    ), f"Expected to make more than 5 requests, but made {requests_made}"

    # The last request should have been rate limited (429)
    assert last_response is not None, "No response received"
    assert (
        last_response.status_code == 429
    ), f"Expected 429, got {last_response.status_code}"

    # Verify the response contains expected rate limit message
    response_text = last_response.text.lower()
    assert (
        "rate_limited" in response_text or "too many requests" in response_text
    ), f"Unexpected response: {response_text}"

    # Verify metrics were incremented
    final_metrics = get_metrics()

    # Total requests should have increased
    requests_increased = (
        final_metrics["requests_total"] >= initial_metrics["requests_total"]
    )
    assert (
        requests_increased
    ), f"Requests metric didn't increase: {initial_metrics['requests_total']} -> {final_metrics['requests_total']}"

    # Rate limited requests should have increased
    rate_limited_increased = (
        final_metrics["rate_limited_total"] > initial_metrics["rate_limited_total"]
    )
    assert (
        rate_limited_increased
    ), f"Rate limited metric didn't increase: {initial_metrics['rate_limited_total']} -> {final_metrics['rate_limited_total']}"

    # Clean up test configuration
    from app.middleware.rate_limit import _test_reset_config

    _test_reset_config()


def test_rate_limit_metrics_endpoint():
    """Test that rate limit metrics are exposed via the metrics endpoint."""

    from app.middleware.rate_limit import get_metrics

    metrics = get_metrics()

    # Verify metrics structure
    expected_keys = {
        "requests_total",
        "rate_limited_total",
        "requests_by_user",
        "requests_by_scope",
        "rate_limited_by_user",
        "rate_limited_by_scope",
    }

    assert all(
        key in metrics for key in expected_keys
    ), f"Missing keys in metrics: {expected_keys - set(metrics.keys())}"

    # All metrics should be integers or dictionaries
    for key, value in metrics.items():
        if key.endswith("_total"):
            assert isinstance(
                value, int
            ), f"Metric {key} should be int, got {type(value)}"
        else:
            assert isinstance(
                value, dict
            ), f"Metric {key} should be dict, got {type(value)}"
