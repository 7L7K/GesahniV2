"""
PHASE 6: Service Level Indicators and Objectives

Concrete targets and alerting thresholds for monitoring and CI testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class SLO:
    """Service Level Objective with concrete targets and thresholds."""
    name: str
    description: str
    sli_name: str
    target: float  # Target percentage (e.g., 99.9 for 99.9%)
    warning_threshold: float  # Warning alert threshold
    critical_threshold: float  # Critical alert threshold
    period_seconds: int  # Evaluation period
    min_sample_size: int  # Minimum samples required for evaluation


@dataclass
class SLIResult:
    """Result of SLI measurement."""
    sli_name: str
    value: float
    target: float
    achieved: bool
    sample_size: int
    period_start: datetime
    period_end: datetime
    details: dict[str, Any]


class SLOMonitor:
    """Monitor and evaluate Service Level Objectives."""

    # PHASE 6: Production SLIs/SLOs
    SLO_DEFINITIONS = {
        # Authentication SLOs
        "auth_success_rate": SLO(
            name="Authentication Success Rate",
            description="Percentage of authentication attempts that succeed",
            sli_name="auth_success_rate",
            target=99.5,  # 99.5% success rate
            warning_threshold=99.0,
            critical_threshold=98.0,
            period_seconds=3600,  # 1 hour
            min_sample_size=10,
        ),

        "auth_latency": SLO(
            name="Authentication Latency",
            description="95th percentile authentication response time",
            sli_name="auth_latency_p95",
            target=0.5,  # 500ms
            warning_threshold=1.0,  # 1s
            critical_threshold=2.0,  # 2s
            period_seconds=900,  # 15 minutes
            min_sample_size=20,
        ),

        # API Availability SLOs
        "api_availability": SLO(
            name="API Availability",
            description="Percentage of API requests that return non-5xx responses",
            sli_name="api_availability",
            target=99.9,  # 99.9% availability
            warning_threshold=99.5,
            critical_threshold=99.0,
            period_seconds=3600,  # 1 hour
            min_sample_size=100,
        ),

        "api_latency": SLO(
            name="API Latency",
            description="95th percentile API response time for successful requests",
            sli_name="api_latency_p95",
            target=2.0,  # 2 seconds
            warning_threshold=5.0,  # 5 seconds
            critical_threshold=10.0,  # 10 seconds
            period_seconds=1800,  # 30 minutes
            min_sample_size=50,
        ),

        # Authorization SLOs
        "authz_success_rate": SLO(
            name="Authorization Success Rate",
            description="Percentage of authorized requests that succeed",
            sli_name="authz_success_rate",
            target=99.9,
            warning_threshold=99.5,
            critical_threshold=99.0,
            period_seconds=3600,
            min_sample_size=100,
        ),

        # WebSocket SLOs
        "ws_connection_success": SLO(
            name="WebSocket Connection Success",
            description="Percentage of WebSocket connection attempts that succeed",
            sli_name="ws_connection_success",
            target=99.0,
            warning_threshold=98.0,
            critical_threshold=95.0,
            period_seconds=3600,
            min_sample_size=10,
        ),

        "ws_message_latency": SLO(
            name="WebSocket Message Latency",
            description="95th percentile WebSocket message round-trip time",
            sli_name="ws_message_latency_p95",
            target=0.1,  # 100ms
            warning_threshold=0.5,  # 500ms
            critical_threshold=1.0,  # 1s
            period_seconds=900,  # 15 minutes
            min_sample_size=20,
        ),

        # Memory and AI SLOs
        "ai_response_success": SLO(
            name="AI Response Success Rate",
            description="Percentage of AI requests that return valid responses",
            sli_name="ai_response_success",
            target=99.0,
            warning_threshold=98.0,
            critical_threshold=95.0,
            period_seconds=1800,
            min_sample_size=30,
        ),

        "ai_response_latency": SLO(
            name="AI Response Latency",
            description="95th percentile AI response time",
            sli_name="ai_response_latency_p95",
            target=5.0,  # 5 seconds
            warning_threshold=15.0,  # 15 seconds
            critical_threshold=30.0,  # 30 seconds
            period_seconds=900,
            min_sample_size=20,
        ),

        # Security SLOs
        "security_incident_rate": SLO(
            name="Security Incident Rate",
            description="Rate of security incidents per hour (should be very low)",
            sli_name="security_incident_rate",
            target=0.1,  # Max 0.1 incidents per hour
            warning_threshold=1.0,
            critical_threshold=5.0,
            period_seconds=3600,
            min_sample_size=1,
        ),

        # Data Integrity SLOs
        "audit_integrity": SLO(
            name="Audit Log Integrity",
            description="Audit log must maintain 100% integrity",
            sli_name="audit_integrity",
            target=100.0,
            warning_threshold=100.0,  # Any failure is warning
            critical_threshold=100.0,  # Any failure is critical
            period_seconds=300,  # 5 minutes
            min_sample_size=1,
        ),

        # Performance SLOs
        "memory_search_latency": SLO(
            name="Memory Search Latency",
            description="95th percentile memory search response time",
            sli_name="memory_search_latency_p95",
            target=1.0,  # 1 second
            warning_threshold=3.0,  # 3 seconds
            critical_threshold=10.0,  # 10 seconds
            period_seconds=900,
            min_sample_size=15,
        ),

        # Error Budget SLOs
        "error_rate_4xx": SLO(
            name="Client Error Rate",
            description="Rate of 4xx errors (excluding auth failures)",
            sli_name="error_rate_4xx",
            target=5.0,  # Max 5% 4xx errors
            warning_threshold=10.0,
            critical_threshold=20.0,
            period_seconds=3600,
            min_sample_size=50,
        ),

        "error_rate_5xx": SLO(
            name="Server Error Rate",
            description="Rate of 5xx errors",
            sli_name="error_rate_5xx",
            target=0.5,  # Max 0.5% 5xx errors
            warning_threshold=1.0,
            critical_threshold=5.0,
            period_seconds=3600,
            min_sample_size=50,
        ),
    }

    def __init__(self):
        self.measurements: dict[str, list[dict[str, Any]]] = {}
        self.last_evaluation: dict[str, datetime] = {}

    def record_measurement(self, sli_name: str, value: float, **metadata):
        """Record an SLI measurement."""
        if sli_name not in self.measurements:
            self.measurements[sli_name] = []

        measurement = {
            "timestamp": datetime.now(),
            "value": value,
            **metadata
        }

        self.measurements[sli_name].append(measurement)

        # Keep only recent measurements (last 24 hours)
        cutoff = datetime.now() - timedelta(hours=24)
        self.measurements[sli_name] = [
            m for m in self.measurements[sli_name]
            if m["timestamp"] > cutoff
        ]

    def evaluate_slo(self, slo: SLO) -> SLIResult:
        """Evaluate an SLO against recent measurements."""
        measurements = self.measurements.get(slo.sli_name, [])
        now = datetime.now()
        period_start = now - timedelta(seconds=slo.period_seconds)

        # Filter measurements in the evaluation period
        period_measurements = [
            m for m in measurements
            if m["timestamp"] >= period_start
        ]

        if len(period_measurements) < slo.min_sample_size:
            return SLIResult(
                sli_name=slo.sli_name,
                value=0.0,
                target=slo.target,
                achieved=False,
                sample_size=len(period_measurements),
                period_start=period_start,
                period_end=now,
                details={"error": "Insufficient sample size"}
            )

        # Calculate the SLI value based on the metric type
        if slo.sli_name.endswith("_rate"):
            # For rates: count of good events / total events
            if slo.sli_name in ["auth_success_rate", "api_availability", "authz_success_rate"]:
                good_count = sum(1 for m in period_measurements if m.get("success", False))
                value = (good_count / len(period_measurements)) * 100
            elif slo.sli_name == "error_rate_4xx":
                error_count = sum(1 for m in period_measurements if 400 <= m.get("status_code", 0) < 500)
                value = (error_count / len(period_measurements)) * 100
            elif slo.sli_name == "error_rate_5xx":
                error_count = sum(1 for m in period_measurements if m.get("status_code", 0) >= 500)
                value = (error_count / len(period_measurements)) * 100
            elif slo.sli_name == "security_incident_rate":
                incident_count = len([m for m in period_measurements if m.get("incident", False)])
                hours = slo.period_seconds / 3600
                value = incident_count / hours
            else:
                value = sum(m["value"] for m in period_measurements) / len(period_measurements)
        elif slo.sli_name.endswith("_latency"):
            # For latency: percentile calculation
            if slo.sli_name.endswith("_p95"):
                sorted_measurements = sorted(period_measurements, key=lambda m: m["value"])
                p95_index = int(len(sorted_measurements) * 0.95)
                value = sorted_measurements[min(p95_index, len(sorted_measurements) - 1)]["value"]
            else:
                value = sum(m["value"] for m in period_measurements) / len(period_measurements)
        else:
            # Default: average
            value = sum(m["value"] for m in period_measurements) / len(period_measurements)

        achieved = value >= slo.target if slo.target > 1 else value <= slo.target

        return SLIResult(
            sli_name=slo.sli_name,
            value=value,
            target=slo.target,
            achieved=achieved,
            sample_size=len(period_measurements),
            period_start=period_start,
            period_end=now,
            details={
                "measurements": len(period_measurements),
                "target_type": "minimum" if slo.target <= 1 else "maximum"
            }
        )

    def get_slo_status(self, slo_name: str) -> SLIResult | None:
        """Get the current status of an SLO."""
        if slo_name not in self.SLO_DEFINITIONS:
            return None

        slo = self.SLO_DEFINITIONS[slo_name]
        return self.evaluate_slo(slo)

    def get_all_slo_statuses(self) -> dict[str, SLIResult]:
        """Get status for all SLOs."""
        results = {}
        for slo_name, slo in self.SLO_DEFINITIONS.items():
            results[slo_name] = self.evaluate_slo(slo)
        return results

    def get_failed_slos(self, critical_only: bool = False) -> list[SLIResult]:
        """Get SLOs that are currently failing."""
        failed = []
        for slo_name, result in self.get_all_slo_statuses().items():
            if not result.achieved:
                if critical_only:
                    slo = self.SLO_DEFINITIONS[slo_name]
                    if result.value <= slo.critical_threshold:
                        failed.append(result)
                else:
                    failed.append(result)
        return failed

    def is_system_healthy(self) -> tuple[bool, list[str]]:
        """Check if the system meets all critical SLOs."""
        failed_critical = []
        for result in self.get_failed_slos(critical_only=True):
            failed_critical.append(f"{result.sli_name}: {result.value:.2f} (target: {result.target:.2f})")

        return len(failed_critical) == 0, failed_critical


# Global SLO monitor instance
slo_monitor = SLOMonitor()


def record_api_request(status_code: int, latency_ms: float, auth_success: bool = True, **metadata):
    """Record an API request for SLO tracking."""
    slo_monitor.record_measurement("api_availability", 1 if status_code < 500 else 0, status_code=status_code, **metadata)
    slo_monitor.record_measurement("api_latency_p95", latency_ms / 1000, status_code=status_code, **metadata)
    slo_monitor.record_measurement("authz_success_rate", 1 if auth_success else 0, status_code=status_code, **metadata)

    if 400 <= status_code < 500:
        slo_monitor.record_measurement("error_rate_4xx", 1, status_code=status_code, **metadata)
    elif status_code >= 500:
        slo_monitor.record_measurement("error_rate_5xx", 1, status_code=status_code, **metadata)


def record_auth_attempt(success: bool, latency_ms: float, **metadata):
    """Record an authentication attempt."""
    slo_monitor.record_measurement("auth_success_rate", 1 if success else 0, **metadata)
    slo_monitor.record_measurement("auth_latency_p95", latency_ms / 1000, **metadata)


def record_ai_request(success: bool, latency_ms: float, **metadata):
    """Record an AI request."""
    slo_monitor.record_measurement("ai_response_success", 1 if success else 0, **metadata)
    slo_monitor.record_measurement("ai_response_latency_p95", latency_ms / 1000, **metadata)


def record_security_incident(incident_type: str, **metadata):
    """Record a security incident."""
    slo_monitor.record_measurement("security_incident_rate", 1, incident=True, incident_type=incident_type, **metadata)


def record_websocket_event(event_type: str, success: bool = True, latency_ms: float | None = None, **metadata):
    """Record a WebSocket event."""
    if event_type == "connection":
        slo_monitor.record_measurement("ws_connection_success", 1 if success else 0, **metadata)
    elif event_type == "message" and latency_ms is not None:
        slo_monitor.record_measurement("ws_message_latency_p95", latency_ms / 1000, **metadata)


def record_memory_search(latency_ms: float, **metadata):
    """Record a memory search operation."""
    slo_monitor.record_measurement("memory_search_latency_p95", latency_ms / 1000, **metadata)


def check_audit_integrity() -> bool:
    """Check audit log integrity for SLO compliance."""
    try:
        from app.audit import verify_audit_integrity
        is_valid, issues = verify_audit_integrity()
        slo_monitor.record_measurement("audit_integrity", 100.0 if is_valid else 0.0, issues=issues)
        return is_valid
    except Exception:
        slo_monitor.record_measurement("audit_integrity", 0.0, error="Exception during integrity check")
        return False


# CI/CD Testing Functions
def run_slo_tests() -> dict[str, Any]:
    """Run SLO tests suitable for CI/CD pipelines."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "slo_results": {},
        "overall_pass": True,
        "failed_slos": [],
        "critical_failures": []
    }

    for slo_name, result in slo_monitor.get_all_slo_statuses().items():
        results["slo_results"][slo_name] = {
            "achieved": result.achieved,
            "value": result.value,
            "target": result.target,
            "sample_size": result.sample_size,
            "details": result.details
        }

        if not result.achieved:
            results["overall_pass"] = False
            results["failed_slos"].append(slo_name)

            # Check if it's a critical failure
            slo = SLOMonitor.SLO_DEFINITIONS[slo_name]
            if result.value <= slo.critical_threshold:
                results["critical_failures"].append(slo_name)

    return results


def assert_slos_in_ci(min_success_rate: float = 0.8) -> None:
    """Assert that SLOs pass for CI/CD with configurable minimum success rate."""
    results = run_slo_tests()

    if not results["overall_pass"]:
        failure_msg = f"SLO tests failed. Failed SLOs: {', '.join(results['failed_slos'])}"
        if results["critical_failures"]:
            failure_msg += f" Critical failures: {', '.join(results['critical_failures'])}"
        raise AssertionError(failure_msg)

    # Check minimum success rate
    total_slos = len(results["slo_results"])
    passed_slos = sum(1 for r in results["slo_results"].values() if r["achieved"])
    success_rate = passed_slos / total_slos if total_slos > 0 else 0

    if success_rate < min_success_rate:
        raise AssertionError(
            ".2%"
        )


__all__ = [
    "SLOMonitor",
    "SLO",
    "SLIResult",
    "slo_monitor",
    "record_api_request",
    "record_auth_attempt",
    "record_ai_request",
    "record_security_incident",
    "record_websocket_event",
    "record_memory_search",
    "check_audit_integrity",
    "run_slo_tests",
    "assert_slos_in_ci",
]
