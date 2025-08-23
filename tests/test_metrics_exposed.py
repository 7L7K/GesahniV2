"""
Phase 6.5.a: Metrics Presence Tests
Tests that Prometheus metrics are properly exposed via /metrics endpoint
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


def test_metrics_endpoint_exists(client):
    """Test that /metrics endpoint exists and returns 200"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"


def test_metrics_expose_http_requests_total(client):
    """Test that http_requests_total metric is exposed"""
    # Make some requests to generate metrics
    client.get("/healthz")
    client.get("/v1/admin/metrics")
    client.post("/v1/admin/config", json={"test": "data"})

    # Check metrics endpoint
    response = client.get("/metrics")
    body = response.text

    assert "http_requests_total" in body
    # Should have different route/method/status combinations
    assert 'method="GET"' in body
    assert 'method="POST"' in body
    assert 'status="200"' in body


def test_metrics_expose_auth_fail_total(client):
    """Test that auth_fail_total metric is exposed"""
    # Make a request with invalid token to trigger auth failure
    response = client.get("/v1/admin/config", headers={"Authorization": "Bearer invalid_token"})
    assert response.status_code == 401

    # Check metrics endpoint
    metrics_response = client.get("/metrics")
    body = metrics_response.text

    assert "auth_fail_total" in body
    assert 'reason="invalid"' in body


def test_metrics_expose_rbac_deny_total(client):
    """Test that rbac_deny_total metric is exposed"""
    # Make a request without proper scope
    response = client.get("/v1/admin/config", headers={"Authorization": "Bearer valid_but_no_scope_token"})
    assert response.status_code in [401, 403]

    # Check metrics endpoint
    metrics_response = client.get("/metrics")
    body = metrics_response.text

    assert "rbac_deny_total" in body


def test_metrics_expose_rate_limited_total(client):
    """Test that rate_limited_total metric is exposed"""
    # Make many rapid requests to potentially trigger rate limiting
    for i in range(100):
        response = client.get("/healthz")
        if response.status_code == 429:
            break

    # Check metrics endpoint
    metrics_response = client.get("/metrics")
    body = metrics_response.text

    # The metric should be present even if not triggered
    assert "rate_limited_total" in body


def test_metrics_expose_latency_histogram(client):
    """Test that http_request_latency_seconds histogram is exposed"""
    # Make some requests to generate latency data
    client.get("/healthz")
    client.get("/v1/admin/metrics")

    # Check metrics endpoint
    response = client.get("/metrics")
    body = response.text

    assert "http_request_latency_seconds" in body
    assert "http_request_latency_seconds_bucket" in body
    assert "http_request_latency_seconds_count" in body
    assert "http_request_latency_seconds_sum" in body


def test_metrics_format_is_prometheus_compliant(client):
    """Test that metrics follow Prometheus format"""
    response = client.get("/metrics")
    body = response.text

    lines = body.strip().split('\n')

    # Each metric line should follow Prometheus format
    metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]

    for line in metric_lines:
        # Should have metric_name{labels} value format or just metric_name value
        if '{' in line:
            # Has labels - find the closing brace
            if '}' in line:
                # Extract the value part after the closing brace
                parts = line.split('}')
                if len(parts) >= 2:
                    value_part = parts[-1].strip()
                else:
                    pytest.fail(f"Invalid metric format: {line}")
            else:
                pytest.fail(f"Metric has opening brace but no closing brace: {line}")
        else:
            # Simple format
            parts = line.split()
            if len(parts) >= 2:
                value_part = parts[-1]
            else:
                pytest.fail(f"Invalid simple metric format: {line}")

        # Value should be numeric
        try:
            float(value_part)
        except ValueError:
            pytest.fail(f"Invalid metric value: {value_part}")


def test_metrics_include_help_comments(client):
    """Test that metrics include HELP comments"""
    response = client.get("/metrics")
    body = response.text

    # Should have HELP comments for our metrics
    assert "# HELP http_requests_total Total HTTP requests" in body
    assert "# HELP http_request_latency_seconds HTTP request latency (seconds)" in body
    assert "# HELP auth_fail_total Authentication failures" in body
    assert "# HELP rbac_deny_total Authorization (scope) denials" in body
    assert "# HELP rate_limited_total Requests rejected by rate limit" in body


def test_metrics_include_type_comments(client):
    """Test that metrics include TYPE comments"""
    response = client.get("/metrics")
    body = response.text

    # Should have TYPE comments for our metrics
    assert "# TYPE http_requests_total counter" in body
    assert "# TYPE http_request_latency_seconds histogram" in body
    assert "# TYPE auth_fail_total counter" in body
    assert "# TYPE rbac_deny_total counter" in body
    assert "# TYPE rate_limited_total counter" in body
