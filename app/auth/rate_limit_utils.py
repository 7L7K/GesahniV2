"""Rate limiting utilities for GesahniV2 authentication."""

import os


def _is_rate_limit_enabled() -> bool:
    """Return True when in-app endpoint rate limits should apply.

    Disabled by default in test unless explicitly enabled, and always disabled
    when RATE_LIMIT_MODE=off.
    """
    try:
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

    Precedence:
    1) JWT_REFRESH_TTL_SECONDS (seconds)
    2) JWT_REFRESH_EXPIRE_MINUTES (minutes → seconds)
    Default: 7 days.
    """
    try:
        v = os.getenv("JWT_REFRESH_TTL_SECONDS")
        if v is not None and str(v).strip() != "":
            return max(1, int(v))
    except Exception:
        pass
    try:
        vmin = os.getenv("JWT_REFRESH_EXPIRE_MINUTES")
        if vmin is not None and str(vmin).strip() != "":
            return max(60, int(vmin) * 60)
    except Exception:
        pass
    return 7 * 24 * 60 * 60
