"""Router budget management functions.

This module contains all budget-related functions and calculations.
No router imports to avoid circular dependencies.
"""

import time

from .policy import ROUTER_BUDGET_MS


def get_remaining_budget(start_time: float) -> float:
    """Calculate remaining budget in seconds based on start time.

    Args:
        start_time: Monotonic start time from time.monotonic()

    Returns:
        Remaining budget in seconds (never negative)
    """
    elapsed_ms = (time.monotonic() - start_time) * 1000
    remaining_ms = max(0, ROUTER_BUDGET_MS - elapsed_ms)
    return remaining_ms / 1000  # Convert to seconds


def is_budget_exceeded(start_time: float) -> bool:
    """Check if the router budget has been exceeded.

    Args:
        start_time: Monotonic start time from time.monotonic()

    Returns:
        True if budget is exceeded, False otherwise
    """
    return get_remaining_budget(start_time) <= 0


def get_budget_timeout_seconds(start_time: float) -> float:
    """Get the remaining budget as a timeout value in seconds.

    Args:
        start_time: Monotonic start time from time.monotonic()

    Returns:
        Remaining budget in seconds, minimum 0.1 to avoid zero timeouts
    """
    return max(0.1, get_remaining_budget(start_time))
