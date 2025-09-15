"""Authentication module for GesahniV2.

This module contains authentication-related constants, utilities, and configurations.
"""

from .constants import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    JWT_ALG,
    JWT_AUD,
    JWT_ISS,
    REFRESH_COOKIE,
    SESSION_COOKIE,
)

# Patch point for tests; real code sets this in startup
user_store = None

# Import legacy auth functions from the main auth module
try:
    from ..api.auth import router
    from ..auth import (
        # Rate limiting constants
        _ATTEMPT_MAX,
        _ATTEMPT_WINDOW,
        _EXPONENTIAL_BACKOFF_THRESHOLD,
        _HARD_LOCKOUT_THRESHOLD,
        _LOCKOUT_SECONDS,
        EXPIRE_MINUTES,
        REFRESH_EXPIRE_MINUTES,
        _attempts,  # Add _attempts to imports
        _backoff_max_ms,
        _backoff_start_ms,
        # Rate limiting functions
        _clear_rate_limit_data,
        _create_session_id,
        _get_rate_limit_stats,
        _get_throttle_status,
        _record_attempt,
        _should_apply_backoff,
        _should_hard_lockout,
        _throttled,
        _verify_session_id,
        pwd_context,
    )
except ImportError:
    # If the auth module doesn't exist yet, define stubs
    def _should_apply_backoff(*args, **kwargs):
        return False  # Default: no backoff

    _backoff_start_ms = 0
    _backoff_max_ms = 0

    def _create_session_id(*args, **kwargs):
        return "dummy_session_id"

    def _verify_session_id(*args, **kwargs):
        return False

    def _record_attempt(*args, **kwargs):
        pass  # Stub function, does nothing

    try:
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    except ImportError:
        pwd_context = None

    EXPIRE_MINUTES = 30
    REFRESH_EXPIRE_MINUTES = 1440

    # Stub rate limiting constants
    _ATTEMPT_MAX = 5
    _ATTEMPT_WINDOW = 300
    _EXPONENTIAL_BACKOFF_THRESHOLD = 3
    _HARD_LOCKOUT_THRESHOLD = 10
    _LOCKOUT_SECONDS = 900
    _attempts = {}  # Add stub for _attempts

    # Stub rate limiting functions
    def _clear_rate_limit_data(*args, **kwargs):
        pass

    def _get_rate_limit_stats(*args, **kwargs):
        return {"count": 0, "last_attempt": 0}

    def _get_throttle_status(*args, **kwargs):
        return {"throttled": False, "wait_time": 0, "should_hard_lockout": False}

    def _should_hard_lockout(*args, **kwargs):
        return False

    def _throttled(*args, **kwargs):
        return None

    # Stub router for when auth module is unavailable
    try:
        from fastapi import APIRouter

        router = APIRouter(tags=["Auth"])
    except ImportError:
        router = None

__all__ = [
    "ACCESS_COOKIE",
    "REFRESH_COOKIE",
    "CSRF_COOKIE",
    "SESSION_COOKIE",
    "JWT_ALG",
    "JWT_ISS",
    "JWT_AUD",
    "CSRF_HEADER",
    "user_store",  # Patch point for tests
    # Legacy auth functions
    "_should_apply_backoff",
    "_backoff_start_ms",
    "_backoff_max_ms",
    "_create_session_id",
    "_verify_session_id",
    "_record_attempt",
    "pwd_context",
    "EXPIRE_MINUTES",
    "REFRESH_EXPIRE_MINUTES",
    # Rate limiting constants
    "_ATTEMPT_MAX",
    "_ATTEMPT_WINDOW",
    "_EXPONENTIAL_BACKOFF_THRESHOLD",
    "_HARD_LOCKOUT_THRESHOLD",
    "_LOCKOUT_SECONDS",
    "_attempts",  # Add _attempts to __all__
    # Rate limiting functions
    "_clear_rate_limit_data",
    "_get_rate_limit_stats",
    "_get_throttle_status",
    "_should_hard_lockout",
    "_throttled",
    # Router
    "router",
]
