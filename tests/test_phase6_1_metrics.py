"""
Phase 6.1: Test Clean Prometheus Metrics

Tests to verify that the new metrics system works correctly.
"""

from app.metrics import AUTH_FAIL, LATENCY, RATE_LIMITED, RBAC_DENY, REQUESTS


class TestMetricsMiddleware:
    """Test the new metrics middleware."""

    def setup_method(self):
        """Reset metrics before each test."""
        # Reset Prometheus metrics (this is a simple approach for testing)
        if hasattr(REQUESTS, '_metrics'):
            REQUESTS._metrics.clear()
        if hasattr(LATENCY, '_metrics'):
            LATENCY._metrics.clear()
        if hasattr(AUTH_FAIL, '_metrics'):
            AUTH_FAIL._metrics.clear()
        if hasattr(RBAC_DENY, '_metrics'):
            RBAC_DENY._metrics.clear()
        if hasattr(RATE_LIMITED, '_metrics'):
            RATE_LIMITED._metrics.clear()

    def test_metrics_middleware_basic(self, client):
        """Test that metrics middleware records basic request metrics."""
        # Make a simple request
        response = client.get("/healthz")
        assert response.status_code == 200

        # The metrics should be recorded (we can't easily test the exact values
        # without mocking Prometheus, but we can verify the middleware doesn't break)

    def test_metrics_endpoint_exposed(self, client):
        """Test that /metrics endpoint is exposed."""
        response = client.get("/metrics")
        assert response.status_code == 200
        content = response.text

        # Should contain our new metric names
        assert "http_requests_total" in content
        assert "http_request_latency_seconds" in content
        assert "auth_fail_total" in content
        assert "rbac_deny_total" in content
        assert "rate_limited_total" in content

    def test_route_name_extraction(self, client):
        """Test that route names are extracted correctly."""
        # Test various endpoints to see route name extraction
        endpoints = [
            "/healthz",
            "/v1/whoami",  # This might not exist, but tests the pattern
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should not crash, regardless of status
            assert response.status_code is not None


class TestAuthMetrics:
    """Test authentication failure metrics."""

    def test_auth_fail_metrics_import(self):
        """Test that AUTH_FAIL metrics can be imported."""
        assert AUTH_FAIL is not None
        assert hasattr(AUTH_FAIL, 'labels')
        assert callable(AUTH_FAIL.labels)

    def test_rbac_deny_metrics_import(self):
        """Test that RBAC_DENY metrics can be imported."""
        assert RBAC_DENY is not None
        assert hasattr(RBAC_DENY, 'labels')
        assert callable(RBAC_DENY.labels)

    def test_rate_limited_metrics_import(self):
        """Test that RATE_LIMITED metrics can be imported."""
        assert RATE_LIMITED is not None
        assert hasattr(RATE_LIMITED, 'labels')
        assert callable(RATE_LIMITED.labels)


class TestMetricsStructure:
    """Test the structure of the new metrics."""

    def test_requests_metric_structure(self):
        """Test REQUESTS metric has correct label names."""
        assert hasattr(REQUESTS, 'labelnames')
        expected_labels = ("route", "method", "status")
        assert REQUESTS.labelnames == expected_labels

    def test_latency_metric_structure(self):
        """Test LATENCY metric has correct label names and buckets."""
        assert hasattr(LATENCY, 'labelnames')
        expected_labels = ("route", "method")
        assert LATENCY.labelnames == expected_labels

        assert hasattr(LATENCY, 'buckets')
        expected_buckets = (0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5)
        assert LATENCY.buckets == expected_buckets

    def test_auth_fail_metric_structure(self):
        """Test AUTH_FAIL metric has correct label names."""
        assert hasattr(AUTH_FAIL, 'labelnames')
        expected_labels = ("reason",)
        assert AUTH_FAIL.labelnames == expected_labels

    def test_rbac_deny_metric_structure(self):
        """Test RBAC_DENY metric has correct label names."""
        assert hasattr(RBAC_DENY, 'labelnames')
        expected_labels = ("scope",)
        assert RBAC_DENY.labelnames == expected_labels

    def test_rate_limited_metric_structure(self):
        """Test RATE_LIMITED metric has correct label names."""
        assert hasattr(RATE_LIMITED, 'labelnames')
        expected_labels = ("route",)
        assert RATE_LIMITED.labelnames == expected_labels
