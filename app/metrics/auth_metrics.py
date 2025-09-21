"""
Authentication and Identity Metrics

This module provides metrics tracking for authentication, legacy sub resolutions,
and identity health monitoring.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


@dataclass
class AuthMetrics:
    """Container for authentication metrics."""
    legacy_sub_resolutions_total: int = 0
    db_uuid_coercion_fail_total: int = 0
    spotify_refresh_fail_total: int = 0
    token_encrypt_bytes_total: int = 0
    token_decrypt_bytes_total: int = 0
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now(UTC)


# Global metrics instance
_metrics = AuthMetrics()


def increment_legacy_sub_resolution(source: str, original_sub: str, resolved_uuid: str) -> None:
    """
    Increment legacy sub resolution counter.
    
    Args:
        source: Source of the legacy sub ("alias" or "username")
        original_sub: Original legacy sub value
        resolved_uuid: Resolved UUID value
    """
    global _metrics
    _metrics.legacy_sub_resolutions_total += 1
    _metrics.last_updated = datetime.now(UTC)
    
    # Log structured warning for monitoring
    logger.warning(
        "legacy_sub_mapped",
        extra={
            "event": "legacy_sub_mapped",
            "source": source,
            "original_sub": original_sub,
            "resolved_uuid": resolved_uuid,
            "resolution_count": _metrics.legacy_sub_resolutions_total,
            "timestamp": _metrics.last_updated.isoformat(),
        }
    )


def increment_db_uuid_coercion_fail(table: str, column: str, error: str) -> None:
    """
    Increment database UUID coercion failure counter.
    
    Args:
        table: Database table name
        column: Column name
        error: Error message
    """
    global _metrics
    _metrics.db_uuid_coercion_fail_total += 1
    _metrics.last_updated = datetime.now(UTC)
    
    # Log structured error for monitoring
    logger.error(
        "db_uuid_coercion_failed",
        extra={
            "event": "db_uuid_coercion_failed",
            "table": table,
            "column": column,
            "error": error,
            "failure_count": _metrics.db_uuid_coercion_fail_total,
            "timestamp": _metrics.last_updated.isoformat(),
        }
    )


def increment_spotify_refresh_fail(reason: str, error: Optional[str] = None) -> None:
    """
    Increment Spotify refresh failure counter.
    
    Args:
        reason: Failure reason (invalid_grant, network, rate_limit, etc.)
        error: Optional error message
    """
    global _metrics
    _metrics.spotify_refresh_fail_total += 1
    _metrics.last_updated = datetime.now(UTC)
    
    # Log structured error for monitoring
    logger.error(
        "spotify_refresh_failed",
        extra={
            "event": "spotify_refresh_failed",
            "reason": reason,
            "error": error,
            "failure_count": _metrics.spotify_refresh_fail_total,
            "timestamp": _metrics.last_updated.isoformat(),
        }
    )


def increment_token_encrypt_bytes(bytes_count: int) -> None:
    """
    Increment token encryption bytes counter.
    
    Args:
        bytes_count: Number of bytes encrypted
    """
    global _metrics
    _metrics.token_encrypt_bytes_total += bytes_count
    _metrics.last_updated = datetime.now(UTC)


def increment_token_decrypt_bytes(bytes_count: int) -> None:
    """
    Increment token decryption bytes counter.
    
    Args:
        bytes_count: Number of bytes decrypted
    """
    global _metrics
    _metrics.token_decrypt_bytes_total += bytes_count
    _metrics.last_updated = datetime.now(UTC)


def get_metrics() -> Dict[str, Any]:
    """
    Get current metrics as a dictionary.
    
    Returns:
        Dictionary containing current metrics
    """
    global _metrics
    return {
        "auth_legacy_sub_resolutions_total": _metrics.legacy_sub_resolutions_total,
        "db_uuid_coercion_fail_total": _metrics.db_uuid_coercion_fail_total,
        "spotify_refresh_fail_total": _metrics.spotify_refresh_fail_total,
        "token_encrypt_bytes_total": _metrics.token_encrypt_bytes_total,
        "token_decrypt_bytes_total": _metrics.token_decrypt_bytes_total,
        "last_updated": _metrics.last_updated.isoformat(),
    }


def get_metrics_summary() -> Dict[str, Any]:
    """
    Get metrics summary for health checks.
    
    Returns:
        Dictionary containing metrics summary
    """
    global _metrics
    return {
        "legacy_resolutions": {
            "total": _metrics.legacy_sub_resolutions_total,
            "status": "healthy" if _metrics.legacy_sub_resolutions_total == 0 else "warning",
        },
        "db_coercion_failures": {
            "total": _metrics.db_uuid_coercion_fail_total,
            "status": "healthy" if _metrics.db_uuid_coercion_fail_total == 0 else "error",
        },
        "spotify_refresh_failures": {
            "total": _metrics.spotify_refresh_fail_total,
            "status": "healthy" if _metrics.spotify_refresh_fail_total == 0 else "warning",
        },
        "token_operations": {
            "encrypt_bytes": _metrics.token_encrypt_bytes_total,
            "decrypt_bytes": _metrics.token_decrypt_bytes_total,
            "status": "healthy",
        },
        "last_updated": _metrics.last_updated.isoformat(),
    }


def reset_metrics() -> None:
    """Reset all metrics to zero."""
    global _metrics
    _metrics = AuthMetrics()


# Prometheus-style metrics for external monitoring systems
def get_prometheus_metrics() -> str:
    """
    Get metrics in Prometheus format.
    
    Returns:
        Prometheus-formatted metrics string
    """
    global _metrics
    return f"""# HELP auth_legacy_sub_resolutions_total Total number of legacy sub resolutions
# TYPE auth_legacy_sub_resolutions_total counter
auth_legacy_sub_resolutions_total {_metrics.legacy_sub_resolutions_total}

# HELP db_uuid_coercion_fail_total Total number of database UUID coercion failures
# TYPE db_uuid_coercion_fail_total counter
db_uuid_coercion_fail_total {_metrics.db_uuid_coercion_fail_total}

# HELP spotify_refresh_fail_total Total number of Spotify refresh failures
# TYPE spotify_refresh_fail_total counter
spotify_refresh_fail_total {_metrics.spotify_refresh_fail_total}

# HELP token_encrypt_bytes_total Total bytes encrypted for tokens
# TYPE token_encrypt_bytes_total counter
token_encrypt_bytes_total {_metrics.token_encrypt_bytes_total}

# HELP token_decrypt_bytes_total Total bytes decrypted for tokens
# TYPE token_decrypt_bytes_total counter
token_decrypt_bytes_total {_metrics.token_decrypt_bytes_total}
"""
