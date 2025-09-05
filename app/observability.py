"""Observability utilities for monitoring and alerting.

Provides golden queries for latency and error rate monitoring.
"""

import logging
from typing import Dict, Any, List
from app.metrics import ASK_LATENCY_MS, ASK_ERRORS_TOTAL, PROMPT_ROUTER_CALLS_TOTAL

logger = logging.getLogger(__name__)


def get_ask_latency_p95_by_backend() -> Dict[str, float]:
    """Get p95 latency by backend for /v1/ask requests.

    Returns:
        Dict mapping backend names to their p95 latency in milliseconds
    """
    try:
        # In a real implementation, this would query Prometheus metrics
        # For now, return mock data showing the metric structure
        return {
            "dryrun": 15.0,
            "openai": 1250.0,
            "llama": 850.0,
        }
    except Exception as e:
        logger.warning(f"Failed to get p95 latency metrics: {e}")
        return {}


def get_ask_error_rate_by_backend() -> Dict[str, Dict[str, float]]:
    """Get error rate by backend and error type for /v1/ask requests.

    Returns:
        Dict mapping backend names to dicts of error_type -> error_rate
    """
    try:
        # In a real implementation, this would query Prometheus metrics
        # For now, return mock data showing the metric structure
        return {
            "dryrun": {
                "timeout": 0.001,
                "error": 0.005,
                "unexpected": 0.0001,
            },
            "openai": {
                "timeout": 0.02,
                "error": 0.08,
                "unexpected": 0.001,
            },
            "llama": {
                "timeout": 0.015,
                "error": 0.06,
                "unexpected": 0.0005,
            },
        }
    except Exception as e:
        logger.warning(f"Failed to get error rate metrics: {e}")
        return {}


def log_ask_observability_summary():
    """Log a summary of current /v1/ask observability metrics."""
    try:
        latency_p95 = get_ask_latency_p95_by_backend()
        error_rates = get_ask_error_rate_by_backend()

        logger.info("ask.observability_summary", extra={
            "latency_p95_by_backend": latency_p95,
            "error_rates_by_backend": error_rates,
            "alerts": _generate_alerts(latency_p95, error_rates),
        })
    except Exception as e:
        logger.error(f"Failed to generate observability summary: {e}")


def _generate_alerts(latency_p95: Dict[str, float], error_rates: Dict[str, Dict[str, float]]) -> List[str]:
    """Generate alerts based on latency and error rate thresholds."""
    alerts = []

    # Alert on high p95 latency
    for backend, p95 in latency_p95.items():
        if backend == "openai" and p95 > 5000:  # 5 seconds
            alerts.append(f"HIGH_LATENCY_OPENAI: p95={p95}ms")
        elif backend == "llama" and p95 > 3000:  # 3 seconds
            alerts.append(f"HIGH_LATENCY_LLAMA: p95={p95}ms")

    # Alert on high error rates
    for backend, error_types in error_rates.items():
        total_error_rate = sum(error_types.values())
        if total_error_rate > 0.1:  # 10% error rate
            alerts.append(f"HIGH_ERROR_RATE_{backend.upper()}: {total_error_rate:.1%}")

        # Alert on timeout rate specifically
        timeout_rate = error_types.get("timeout", 0)
        if timeout_rate > 0.05:  # 5% timeout rate
            alerts.append(f"HIGH_TIMEOUT_RATE_{backend.upper()}: {timeout_rate:.1%}")

    return alerts


# Golden query examples for documentation
GOLDEN_QUERIES = {
    "p95_latency_by_backend": """
        histogram_quantile(0.95, sum(rate(ask_latency_ms_bucket[5m])) by (le, backend))
    """,

    "error_rate_by_backend": """
        sum(rate(ask_errors_total[5m])) by (backend) /
        sum(rate(prompt_router_calls_total[5m])) by (backend)
    """,

    "error_rate_by_backend_and_type": """
        sum(rate(ask_errors_total[5m])) by (backend, error_type) /
        sum(rate(prompt_router_calls_total[5m])) by (backend)
    """,
}
