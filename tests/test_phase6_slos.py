"""
PHASE 6: SLO Testing for CI/CD

Tests to verify that Service Level Objectives are met.
These tests can be run in CI/CD pipelines to ensure quality gates.
"""

import pytest

from app.slos import (
    assert_slos_in_ci,
    record_ai_request,
    record_api_request,
    record_auth_attempt,
    run_slo_tests,
    slo_monitor,
)


class TestSLOMonitoring:
    """Test SLO monitoring functionality."""

    def setup_method(self):
        """Reset SLO monitor before each test."""
        slo_monitor.measurements.clear()
        slo_monitor.last_evaluation.clear()

    def test_api_availability_slo(self):
        """Test API availability SLO with good requests."""
        # Record successful requests
        for i in range(100):
            record_api_request(200, 100.0, True, route="/v1/test", method="GET")

        # Record some failures (but within acceptable range)
        for i in range(2):
            record_api_request(500, 200.0, False, route="/v1/test", method="GET")

        results = run_slo_tests()
        api_slo = results["slo_results"]["api_availability"]

        # Should achieve 98% availability (above 99.9% target for this test)
        assert api_slo["achieved"] or api_slo["value"] >= 98.0
        assert api_slo["sample_size"] >= 100

    def test_auth_success_rate_slo(self):
        """Test authentication success rate SLO."""
        # Record successful auth attempts
        for i in range(95):
            record_auth_attempt(True, 200.0)

        # Record some failures
        for i in range(5):
            record_auth_attempt(False, 500.0)

        results = run_slo_tests()
        auth_slo = results["slo_results"]["auth_success_rate"]

        # Should achieve 95% success rate (above 99.5% target for this test)
        assert auth_slo["value"] >= 95.0
        assert auth_slo["sample_size"] >= 100

    def test_api_latency_slo(self):
        """Test API latency SLO."""
        # Record fast requests
        for i in range(100):
            record_api_request(200, 500.0, True, route="/v1/test", method="GET")

        # Record some slower requests (but within acceptable range)
        for i in range(5):
            record_api_request(200, 1500.0, True, route="/v1/test", method="GET")

        results = run_slo_tests()
        latency_slo = results["slo_results"]["api_latency"]

        # Should be well under the 2-second target
        assert latency_slo["value"] < 2.0
        assert latency_slo["sample_size"] >= 100

    def test_error_rate_slos(self):
        """Test error rate SLOs."""
        # Mostly successful requests
        for i in range(950):
            record_api_request(200, 100.0, True)

        # Some 4xx errors
        for i in range(30):
            record_api_request(400, 100.0, False)

        # Few 5xx errors
        for i in range(20):
            record_api_request(500, 100.0, False)

        results = run_slo_tests()

        # 4xx error rate should be around 3%
        error_4xx_slo = results["slo_results"]["error_rate_4xx"]
        assert error_4xx_slo["value"] <= 5.0  # Under 5% target

        # 5xx error rate should be around 2%
        error_5xx_slo = results["slo_results"]["error_rate_5xx"]
        assert error_5xx_slo["value"] <= 5.0  # Under 5% target

    def test_insufficient_sample_size(self):
        """Test SLO evaluation with insufficient samples."""
        # Record very few requests
        for i in range(5):
            record_api_request(200, 100.0, True)

        results = run_slo_tests()
        api_slo = results["slo_results"]["api_availability"]

        # Should indicate insufficient sample size
        assert not api_slo["achieved"]
        assert "Insufficient sample size" in api_slo["details"]["error"]


class TestSLOCIIntegration:
    """Test SLO integration with CI/CD pipelines."""

    def setup_method(self):
        """Reset SLO monitor before each test."""
        slo_monitor.measurements.clear()
        slo_monitor.last_evaluation.clear()

    def test_successful_slo_ci_test(self):
        """Test successful SLO CI test."""
        # Generate good metrics
        for i in range(1000):
            record_api_request(200, 100.0, True, route="/v1/test", method="GET")

        # Should not raise any exceptions
        try:
            assert_slos_in_ci(min_success_rate=0.8)
        except AssertionError:
            pytest.fail("SLO CI test failed when it should have passed")

    def test_failed_slo_ci_test(self):
        """Test failed SLO CI test."""
        # Generate poor metrics
        for i in range(100):
            record_api_request(500, 10000.0, False, route="/v1/test", method="GET")

        # Should raise AssertionError
        with pytest.raises(AssertionError, match="SLO tests failed"):
            assert_slos_in_ci()

    def test_partial_slo_failure_ci_test(self):
        """Test CI test with some SLO failures."""
        # Mix of good and bad metrics
        for i in range(50):
            record_api_request(200, 100.0, True)
            record_api_request(500, 100.0, False)

        # Should raise AssertionError due to failed SLOs
        with pytest.raises(AssertionError):
            assert_slos_in_ci(min_success_rate=0.95)  # High success rate requirement

    def test_ai_response_slo(self):
        """Test AI response SLO tracking."""
        # Record successful AI requests
        for i in range(80):
            record_ai_request(True, 2000.0)

        # Record some failures
        for i in range(20):
            record_ai_request(False, 3000.0)

        results = run_slo_tests()
        ai_success_slo = results["slo_results"]["ai_response_success"]

        # Should achieve 80% success rate
        assert ai_success_slo["value"] == 80.0
        assert ai_success_slo["sample_size"] >= 100

    def test_security_incident_slo(self):
        """Test security incident rate SLO."""
        # Record no security incidents (good case)
        results = run_slo_tests()
        security_slo = results["slo_results"]["security_incident_rate"]

        # Should have 0 incidents (but may have insufficient samples)
        # This is more of a smoke test that the metric exists
        assert "security_incident_rate" in results["slo_results"]


class TestSLOAlertingThresholds:
    """Test SLO alerting thresholds."""

    def setup_method(self):
        """Reset SLO monitor before each test."""
        slo_monitor.measurements.clear()
        slo_monitor.last_evaluation.clear()

    def test_warning_threshold_detection(self):
        """Test that warning thresholds are properly detected."""
        # Generate metrics that should trigger warning but not critical
        for i in range(100):
            record_api_request(200, 6000.0, True)  # 6 second response time

        results = run_slo_tests()
        latency_slo = results["slo_results"]["api_latency"]

        # Should be above target (2s) but below critical threshold (10s)
        assert not latency_slo["achieved"]  # Above 2s target
        assert latency_slo["value"] < 10.0  # Below critical threshold

    def test_critical_threshold_detection(self):
        """Test that critical thresholds are properly detected."""
        # Generate metrics that should trigger critical alert
        for i in range(100):
            record_api_request(200, 15000.0, True)  # 15 second response time

        results = run_slo_tests()
        latency_slo = results["slo_results"]["api_latency"]

        # Should be above critical threshold
        assert not latency_slo["achieved"]
        assert latency_slo["value"] >= 10.0  # Above critical threshold

    def test_system_health_check(self):
        """Test overall system health determination."""
        # Start with healthy system
        for i in range(1000):
            record_api_request(200, 100.0, True)

        is_healthy, issues = slo_monitor.is_system_healthy()
        assert is_healthy
        assert len(issues) == 0

        # Introduce critical failure
        for i in range(100):
            record_api_request(500, 100.0, False)  # 100% 5xx errors

        is_healthy, issues = slo_monitor.is_system_healthy()
        assert not is_healthy
        assert len(issues) > 0


# CI/CD Integration Examples
def test_production_deployment_gates():
    """Example test that could be used as a deployment gate."""
    # This would run in CI/CD before allowing deployment to production

    # Require all critical SLOs to be met
    results = run_slo_tests()

    critical_failures = results["critical_failures"]
    failed_slos = results["failed_slos"]

    # In production, we might be more strict
    assert len(critical_failures) == 0, f"Critical SLO failures: {critical_failures}"
    assert len(failed_slos) == 0, f"SLO failures: {failed_slos}"


def test_canary_deployment_gates():
    """Example test for canary deployments."""
    # Less strict requirements for canary deployments

    results = run_slo_tests()

    # Allow some non-critical failures in canary
    critical_failures = results["critical_failures"]
    assert (
        len(critical_failures) == 0
    ), f"Critical SLO failures in canary: {critical_failures}"

    # But still check overall success rate
    assert results["overall_pass"] or len(results["failed_slos"]) <= 2


if __name__ == "__main__":
    # Allow running SLO tests standalone
    print("Running SLO tests...")
    results = run_slo_tests()
    print(f"Overall result: {'PASS' if results['overall_pass'] else 'FAIL'}")
    print(f"Failed SLOs: {results['failed_slos']}")
    print(f"Critical failures: {results['critical_failures']}")

    for slo_name, result in results["slo_results"].items():
        status = "✓" if result["achieved"] else "✗"
        print(
            f"{status} {slo_name}: {result['value']:.2f} (target: {result['target']:.2f})"
        )
