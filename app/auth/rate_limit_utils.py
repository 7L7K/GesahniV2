"""Rate limiting utilities for GesahniV2 authentication."""

import os


def _is_rate_limit_enabled() -> bool:
    """Return True when in-app endpoint rate limits should apply.

    Disabled by default in test unless explicitly enabled, and always disabled
    when RATE_LIMIT_MODE=off or RATE_LIMIT_ENABLED=0.
    """
    try:
        # Check if rate limiting is explicitly disabled
        enabled = (os.getenv("RATE_LIMIT_ENABLED", "1").strip().lower())
        if enabled in {"0", "false", "no", "off"}:
            return False
        
        v = (os.getenv("RATE_LIMIT_MODE") or "").strip().lower()
        if v == "off":
            return False
        in_test = (os.getenv("ENV", "").strip().lower() == "test") or bool(
            os.getenv("PYTEST_RUNNING") or os.getenv("PYTEST_CURRENT_TEST")
        )
        if in_test and (
            os.getenv("ENABLE_RATE_LIMIT_IN_TESTS", "0").strip().lower()
            not in {"1", "true", "yes", "on"}
        ):
            return False
    except Exception:
        pass
    return True


def _get_refresh_ttl_seconds() -> int:
    """Return refresh token TTL in seconds using consistent precedence.
    
    Order: RATE_LIMIT_REFRESH_TTL > JWT_REFRESH_EXPIRE_MINUTES > 1440 minutes
    """
    try:
        # Check for explicit rate limit refresh TTL
        ttl_str = os.getenv("RATE_LIMIT_REFRESH_TTL")
        if ttl_str:
            return int(ttl_str.strip())
        
        # Fall back to JWT refresh expire minutes
        refresh_minutes = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))
        return refresh_minutes * 60
    except Exception:
        return 86400  # Default to 24 hours


def _get_rate_limit_per_minute() -> int:
    """Return rate limit per minute from environment or default."""
    try:
        return int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
    except Exception:
        return 60
