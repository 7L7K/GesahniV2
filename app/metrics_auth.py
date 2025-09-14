"""
Authentication metrics for monitoring refresh operations and security events.

This module provides Prometheus metrics for:
- Lazy refresh operations
- Refresh token rotation
- Replay protection events
- Authentication failures and successes
"""

from __future__ import annotations

try:
    from prometheus_client import Counter, Gauge, Histogram
except ImportError:
    # Fallback for environments without prometheus
    class Counter:
        def __init__(self, name, documentation, labelnames=None):
            self.name = name
            self.documentation = documentation
            self.labelnames = labelnames or []

        def labels(self, **kwargs):
            return self

        def inc(self, value=1):
            pass

    class Histogram:
        def __init__(self, name, documentation, labelnames=None, buckets=None):
            self.name = name
            self.documentation = documentation
            self.labelnames = labelnames or []
            self.buckets = buckets

        def labels(self, **kwargs):
            return self

        def observe(self, value):
            pass

    class Gauge:
        def __init__(self, name, documentation, labelnames=None):
            self.name = name
            self.documentation = documentation
            self.labelnames = labelnames or []

        def labels(self, **kwargs):
            return self

        def set(self, value):
            return self

        def inc(self, value=1):
            return self

        def dec(self, value=1):
            return self


# Lazy refresh metrics (using unique names to avoid conflicts)
AUTH_LAZY_REFRESH_V2 = Counter(
    "auth_lazy_refresh_v2_total",
    "Total number of lazy refresh operations (v2)",
    ["source", "result"],
)

# Refresh rotation metrics
AUTH_REFRESH_ROTATION = Counter(
    "auth_refresh_rotation_total",
    "Total number of refresh token rotations",
    ["result", "reason"],
)

# Replay protection metrics
AUTH_REPLAY_PROTECTION = Counter(
    "auth_replay_protection_total",
    "Total number of replay protection events",
    ["action", "reason"],
)

# Refresh operation latency
AUTH_REFRESH_LATENCY = Histogram(
    "auth_refresh_latency_seconds",
    "Latency of refresh operations",
    ["operation"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# Token validation metrics
AUTH_TOKEN_VALIDATION = Counter(
    "auth_token_validation_total",
    "Total number of token validations",
    ["token_type", "result"],
)

# Session metrics
AUTH_SESSION_OPERATIONS = Counter(
    "auth_session_operations_total",
    "Total number of session operations",
    ["operation", "result"],
)

# Rate limiting metrics for auth operations
AUTH_RATE_LIMIT = Counter(
    "auth_rate_limit_total",
    "Total number of rate limit events",
    ["operation", "result"],
)

# Concurrent request metrics
AUTH_CONCURRENT_REQUESTS = Counter(
    "auth_concurrent_requests_total",
    "Total number of concurrent request handling",
    ["action", "reason"],
)

# JWT leeway metrics
AUTH_JWT_LEEWAY_USAGE = Histogram(
    "auth_jwt_leeway_usage_seconds",
    "JWT leeway usage in seconds",
    ["operation"],
    buckets=[0, 10, 30, 60, 120, 300],
)

# Family revocation metrics
AUTH_FAMILY_REVOCATION = Counter(
    "auth_family_revocation_total",
    "Total number of refresh token family revocations",
    ["reason"],
)

# Device-bound session metrics
AUTH_DEVICE_BOUND_SESSIONS = Counter(
    "auth_device_bound_sessions_total",
    "Total number of device-bound session operations",
    ["operation", "device_type"],
)

# Active session gauge
AUTH_ACTIVE_SESSIONS = Gauge(
    "auth_active_sessions", "Number of currently active sessions", ["session_type"]
)

# Failed authentication attempts by IP
AUTH_FAILED_ATTEMPTS_IP = Counter(
    "auth_failed_attempts_ip_total",
    "Total number of failed authentication attempts by IP",
    ["ip_hash", "reason"],
)

# Token expiration metrics
AUTH_TOKEN_EXPIRATION = Histogram(
    "auth_token_expiration_seconds",
    "Time until token expiration",
    ["token_type"],
    buckets=[60, 300, 900, 3600, 7200, 21600, 43200, 86400],
)


def record_lazy_refresh(source: str, result: str) -> None:
    """Record a lazy refresh operation."""
    try:
        AUTH_LAZY_REFRESH.labels(source=source, result=result).inc()
    except Exception:
        pass  # Silently fail if metrics are disabled


def record_refresh_rotation(result: str, reason: str = "") -> None:
    """Record a refresh token rotation."""
    try:
        AUTH_REFRESH_ROTATION.labels(result=result, reason=reason).inc()
    except Exception:
        pass


def record_replay_protection(action: str, reason: str = "") -> None:
    """Record a replay protection event."""
    try:
        AUTH_REPLAY_PROTECTION.labels(action=action, reason=reason).inc()
    except Exception:
        pass


def record_refresh_latency(operation: str, duration_seconds: float) -> None:
    """Record refresh operation latency."""
    try:
        AUTH_REFRESH_LATENCY.labels(operation=operation).observe(duration_seconds)
    except Exception:
        pass


def record_token_validation(token_type: str, result: str) -> None:
    """Record token validation result."""
    try:
        AUTH_TOKEN_VALIDATION.labels(token_type=token_type, result=result).inc()
    except Exception:
        pass


def record_session_operation(operation: str, result: str) -> None:
    """Record session operation."""
    try:
        AUTH_SESSION_OPERATIONS.labels(operation=operation, result=result).inc()
    except Exception:
        pass


def record_rate_limit(operation: str, result: str) -> None:
    """Record rate limiting event."""
    try:
        AUTH_RATE_LIMIT.labels(operation=operation, result=result).inc()
    except Exception:
        pass


def record_concurrent_request(action: str, reason: str = "") -> None:
    """Record concurrent request handling."""
    try:
        AUTH_CONCURRENT_REQUESTS.labels(action=action, reason=reason).inc()
    except Exception:
        pass


def record_jwt_leeway_usage(operation: str, leeway_seconds: float) -> None:
    """Record JWT leeway usage."""
    try:
        AUTH_JWT_LEEWAY_USAGE.labels(operation=operation).observe(leeway_seconds)
    except Exception:
        pass


def record_family_revocation(reason: str) -> None:
    """Record family revocation."""
    try:
        AUTH_FAMILY_REVOCATION.labels(reason=reason).inc()
    except Exception:
        pass


def record_device_bound_session(operation: str, device_type: str = "unknown") -> None:
    """Record device-bound session operation."""
    try:
        AUTH_DEVICE_BOUND_SESSIONS.labels(
            operation=operation, device_type=device_type
        ).inc()
    except Exception:
        pass


def update_active_sessions(session_type: str, count: int) -> None:
    """Update active sessions gauge."""
    try:
        AUTH_ACTIVE_SESSIONS.labels(session_type=session_type).set(count)
    except Exception:
        pass


def record_failed_attempt_ip(ip_hash: str, reason: str) -> None:
    """Record failed authentication attempt by IP."""
    try:
        AUTH_FAILED_ATTEMPTS_IP.labels(ip_hash=ip_hash, reason=reason).inc()
    except Exception:
        pass


def record_token_expiration(token_type: str, seconds_until_expiry: float) -> None:
    """Record time until token expiration."""
    try:
        AUTH_TOKEN_EXPIRATION.labels(token_type=token_type).observe(
            seconds_until_expiry
        )
    except Exception:
        pass


# Convenience functions for common operations
def lazy_refresh_minted(source: str = "deps") -> None:
    """Record successful lazy refresh."""
    record_lazy_refresh_v2(source, "minted")


def lazy_refresh_skipped(source: str = "deps") -> None:
    """Record skipped lazy refresh."""
    record_lazy_refresh_v2(source, "skipped")


def lazy_refresh_failed(source: str = "deps") -> None:
    """Record failed lazy refresh."""
    record_lazy_refresh_v2(source, "failed")


def record_lazy_refresh_v2(source: str, result: str) -> None:
    """Record a lazy refresh operation (v2)."""
    try:
        AUTH_LAZY_REFRESH_V2.labels(source=source, result=result).inc()
    except Exception:
        pass


def refresh_rotation_success() -> None:
    """Record successful refresh rotation."""
    record_refresh_rotation("success")


def refresh_rotation_failed(reason: str = "unknown") -> None:
    """Record failed refresh rotation."""
    record_refresh_rotation("failed", reason)


def replay_detected() -> None:
    """Record replay protection trigger."""
    record_replay_protection("blocked", "replay_detected")


def concurrent_allowed() -> None:
    """Record allowed concurrent request."""
    record_replay_protection("allowed", "concurrent_request")


def family_revoked_security() -> None:
    """Record family revocation due to security event."""
    record_family_revocation("security")


def family_revoked_manual() -> None:
    """Record manual family revocation."""
    record_family_revocation("manual")


__all__ = [
    # Core metrics
    "AUTH_LAZY_REFRESH_V2",
    "AUTH_REFRESH_ROTATION",
    "AUTH_REPLAY_PROTECTION",
    "AUTH_REFRESH_LATENCY",
    "AUTH_TOKEN_VALIDATION",
    "AUTH_SESSION_OPERATIONS",
    "AUTH_RATE_LIMIT",
    "AUTH_CONCURRENT_REQUESTS",
    "AUTH_JWT_LEEWAY_USAGE",
    "AUTH_FAMILY_REVOCATION",
    "AUTH_DEVICE_BOUND_SESSIONS",
    "AUTH_ACTIVE_SESSIONS",
    "AUTH_FAILED_ATTEMPTS_IP",
    "AUTH_TOKEN_EXPIRATION",
    # Recording functions
    "record_lazy_refresh",
    "record_lazy_refresh_v2",
    "record_refresh_rotation",
    "record_replay_protection",
    "record_refresh_latency",
    "record_token_validation",
    "record_session_operation",
    "record_rate_limit",
    "record_concurrent_request",
    "record_jwt_leeway_usage",
    "record_family_revocation",
    "record_device_bound_session",
    "update_active_sessions",
    "record_failed_attempt_ip",
    "record_token_expiration",
    # Convenience functions
    "lazy_refresh_minted",
    "lazy_refresh_skipped",
    "lazy_refresh_failed",
    "refresh_rotation_success",
    "refresh_rotation_failed",
    "replay_detected",
    "concurrent_allowed",
    "family_revoked_security",
    "family_revoked_manual",
]
