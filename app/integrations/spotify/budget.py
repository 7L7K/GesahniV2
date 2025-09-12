from __future__ import annotations

import asyncio
import time

from ...budget import get_budget_state


class SpotifyBudgetManager:
    """Manages timeouts, backoff, and budget constraints for Spotify API calls."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._backoff_until: float = 0.0
        self._backoff_multiplier: float = 1.0

    def get_timeout(self) -> float:
        """Get appropriate timeout based on budget state and backoff."""
        # Check if we're in backoff period
        if time.time() < self._backoff_until:
            return 0.0  # Immediate timeout if in backoff

        # Get base timeout from budget state
        budget_state = get_budget_state(self.user_id)

        # Default timeout
        base_timeout = 30.0

        # Reduce timeout under budget pressure
        if budget_state.get("reply_len_target") == "short":
            base_timeout = min(base_timeout, 10.0)

        return base_timeout

    def is_budget_exceeded(self) -> bool:
        """Check if user is over budget limits."""
        budget_state = get_budget_state(self.user_id)
        return not budget_state.get("escalate_allowed", True)

    def apply_backoff(self, retry_after: int | None = None) -> None:
        """Apply exponential backoff after a failure."""
        now = time.time()

        if retry_after:
            # Use Spotify's Retry-After header if provided
            self._backoff_until = now + retry_after
            self._backoff_multiplier = 1.0  # Reset multiplier
        else:
            # Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 60s
            delay = min(1.0 * (2 ** (self._backoff_multiplier - 1)), 60.0)
            self._backoff_until = now + delay
            self._backoff_multiplier = min(self._backoff_multiplier + 1, 6)  # Cap at 2^5 = 32s

    def clear_backoff(self) -> None:
        """Clear backoff state after successful request."""
        self._backoff_until = 0.0
        self._backoff_multiplier = 1.0

    def get_backoff_remaining(self) -> float:
        """Get remaining backoff time in seconds."""
        return max(0.0, self._backoff_until - time.time())

    async def wait_for_backoff(self) -> None:
        """Wait until backoff period is over."""
        remaining = self.get_backoff_remaining()
        if remaining > 0:
            await asyncio.sleep(remaining)


# Global budget manager instances cache
_budget_managers: dict[str, SpotifyBudgetManager] = {}


def get_spotify_budget_manager(user_id: str) -> SpotifyBudgetManager:
    """Get or create a budget manager for the user."""
    if user_id not in _budget_managers:
        _budget_managers[user_id] = SpotifyBudgetManager(user_id)
    return _budget_managers[user_id]
