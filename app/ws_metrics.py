"""
WebSocket Observability Metrics

Tracks WebSocket connection lifecycle, message throughput, and error rates.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Global metrics storage
_ws_metrics: dict[str, Any] = {
    "connections_active": 0,
    "connections_total": 0,
    "connections_by_endpoint": {},
    "messages_sent_total": 0,
    "messages_received_total": 0,
    "messages_failed_total": 0,
    "broadcasts_total": 0,
    "broadcasts_failed_total": 0,
    "auth_attempts_total": 0,
    "auth_success_total": 0,
    "auth_fail_total": 0,
    "errors_by_type": {},
    "connection_duration_avg": 0.0,
    "heartbeat_sent_total": 0,
    "heartbeat_failed_total": 0,
}


def record_ws_connection(endpoint: str, user_id: str):
    """Record a new WebSocket connection."""
    _ws_metrics["connections_active"] += 1
    _ws_metrics["connections_total"] += 1

    if endpoint not in _ws_metrics["connections_by_endpoint"]:
        _ws_metrics["connections_by_endpoint"][endpoint] = 0
    _ws_metrics["connections_by_endpoint"][endpoint] += 1

    logger.info("ws.metrics.connection: endpoint=%s user_id=%s active=%d",
               endpoint, user_id, _ws_metrics["connections_active"])


def record_ws_disconnection(endpoint: str, user_id: str, duration: float):
    """Record a WebSocket disconnection."""
    _ws_metrics["connections_active"] = max(0, _ws_metrics["connections_active"] - 1)

    if endpoint in _ws_metrics["connections_by_endpoint"]:
        _ws_metrics["connections_by_endpoint"][endpoint] = max(0, _ws_metrics["connections_by_endpoint"][endpoint] - 1)

    # Update average connection duration
    current_avg = _ws_metrics["connection_duration_avg"]
    total_connections = _ws_metrics["connections_total"]
    if total_connections > 0:
        _ws_metrics["connection_duration_avg"] = (current_avg * (total_connections - 1) + duration) / total_connections

    logger.info("ws.metrics.disconnection: endpoint=%s user_id=%s duration=%.2f active=%d",
               endpoint, user_id, duration, _ws_metrics["connections_active"])


def record_ws_message_sent():
    """Record a message sent."""
    _ws_metrics["messages_sent_total"] += 1


def record_ws_message_received():
    """Record a message received."""
    _ws_metrics["messages_received_total"] += 1


def record_ws_message_failed():
    """Record a message send failure."""
    _ws_metrics["messages_failed_total"] += 1


def record_ws_broadcast():
    """Record a broadcast operation."""
    _ws_metrics["broadcasts_total"] += 1


def record_ws_broadcast_failed():
    """Record a broadcast failure."""
    _ws_metrics["broadcasts_failed_total"] += 1


def record_ws_auth_attempt():
    """Record an authentication attempt."""
    _ws_metrics["auth_attempts_total"] += 1


def record_ws_auth_success():
    """Record a successful authentication."""
    _ws_metrics["auth_success_total"] += 1


def record_ws_auth_failure(reason: str):
    """Record an authentication failure."""
    _ws_metrics["auth_fail_total"] += 1

    if reason not in _ws_metrics["errors_by_type"]:
        _ws_metrics["errors_by_type"][reason] = 0
    _ws_metrics["errors_by_type"][reason] += 1

    logger.warning("ws.metrics.auth_failure: reason=%s total_failures=%d", reason, _ws_metrics["auth_fail_total"])


def record_ws_error(error_type: str, endpoint: str = "unknown"):
    """Record a WebSocket error."""
    if error_type not in _ws_metrics["errors_by_type"]:
        _ws_metrics["errors_by_type"][error_type] = 0
    _ws_metrics["errors_by_type"][error_type] += 1

    logger.error("ws.metrics.error: type=%s endpoint=%s total_errors=%d",
                error_type, endpoint, _ws_metrics["errors_by_type"][error_type])


def record_ws_heartbeat_sent():
    """Record a heartbeat sent."""
    _ws_metrics["heartbeat_sent_total"] += 1


def record_ws_heartbeat_failed():
    """Record a heartbeat failure."""
    _ws_metrics["heartbeat_failed_total"] += 1


def get_ws_metrics() -> dict[str, Any]:
    """Get current WebSocket metrics."""
    # Calculate rates (these would be better with time windows in a real implementation)
    metrics = _ws_metrics.copy()

    # Add computed metrics
    total_auth = metrics["auth_attempts_total"]
    if total_auth > 0:
        metrics["auth_success_rate"] = metrics["auth_success_total"] / total_auth
    else:
        metrics["auth_success_rate"] = 0.0

    total_messages = metrics["messages_sent_total"] + metrics["messages_failed_total"]
    if total_messages > 0:
        metrics["message_success_rate"] = metrics["messages_sent_total"] / total_messages
    else:
        metrics["message_success_rate"] = 0.0

    total_broadcasts = metrics["broadcasts_total"] + metrics["broadcasts_failed_total"]
    if total_broadcasts > 0:
        metrics["broadcast_success_rate"] = metrics["broadcasts_total"] / total_broadcasts
    else:
        metrics["broadcast_success_rate"] = 0.0

    total_heartbeats = metrics["heartbeat_sent_total"] + metrics["heartbeat_failed_total"]
    if total_heartbeats > 0:
        metrics["heartbeat_success_rate"] = metrics["heartbeat_sent_total"] / total_heartbeats
    else:
        metrics["heartbeat_success_rate"] = 0.0

    return metrics


def reset_ws_metrics():
    """Reset all WebSocket metrics (useful for testing)."""
    global _ws_metrics
    _ws_metrics = {
        "connections_active": 0,
        "connections_total": 0,
        "connections_by_endpoint": {},
        "messages_sent_total": 0,
        "messages_received_total": 0,
        "messages_failed_total": 0,
        "broadcasts_total": 0,
        "broadcasts_failed_total": 0,
        "auth_attempts_total": 0,
        "auth_success_total": 0,
        "auth_fail_total": 0,
        "errors_by_type": {},
        "connection_duration_avg": 0.0,
        "heartbeat_sent_total": 0,
        "heartbeat_failed_total": 0,
    }


# Prometheus-style metric formatting
def format_prometheus_metrics() -> str:
    """Format metrics in Prometheus exposition format."""
    metrics = get_ws_metrics()
    lines = []

    lines.append("# HELP ws_connections_active Current number of active WebSocket connections")
    lines.append("# TYPE ws_connections_active gauge")
    lines.append(f"ws_connections_active {metrics['connections_active']}")

    lines.append("# HELP ws_connections_total Total number of WebSocket connections")
    lines.append("# TYPE ws_connections_total counter")
    lines.append(f"ws_connections_total {metrics['connections_total']}")

    lines.append("# HELP ws_messages_sent_total Total messages sent")
    lines.append("# TYPE ws_messages_sent_total counter")
    lines.append(f"ws_messages_sent_total {metrics['messages_sent_total']}")

    lines.append("# HELP ws_messages_received_total Total messages received")
    lines.append("# TYPE ws_messages_received_total counter")
    lines.append(f"ws_messages_received_total {metrics['messages_received_total']}")

    lines.append("# HELP ws_broadcasts_total Total broadcast operations")
    lines.append("# TYPE ws_broadcasts_total counter")
    lines.append(f"ws_broadcasts_total {metrics['broadcasts_total']}")

    lines.append("# HELP ws_auth_attempts_total Total authentication attempts")
    lines.append("# TYPE ws_auth_attempts_total counter")
    lines.append(f"ws_auth_attempts_total {metrics['auth_attempts_total']}")

    lines.append("# HELP ws_auth_success_rate Authentication success rate")
    lines.append("# TYPE ws_auth_success_rate gauge")
    lines.append(f"ws_auth_success_rate {metrics['auth_success_rate']}")

    # Add endpoint-specific metrics
    for endpoint, count in metrics["connections_by_endpoint"].items():
        lines.append("# HELP ws_connections_by_endpoint Connections by endpoint")
        lines.append("# TYPE ws_connections_by_endpoint gauge")
        lines.append(f'ws_connections_by_endpoint{{endpoint="{endpoint}"}} {count}')

    return "\n".join(lines)
