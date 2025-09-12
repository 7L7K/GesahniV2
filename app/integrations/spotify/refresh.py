from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .client import SpotifyAuthError, SpotifyClient

logger = logging.getLogger(__name__)


class RefreshHelper:
    """Generic refresh helper that can work with different providers."""

    def __init__(self):
        self._refreshing: dict[str, asyncio.Lock] = {}

    async def refresh_if_401(
        self,
        user_id: str,
        operation: Callable[[], Awaitable[Any]],
        refresh_func: Callable[[], Awaitable[None]],
        max_retries: int = 1
    ) -> Any:
        """
        Generic refresh helper that handles 401 errors by refreshing tokens.

        Args:
            user_id: User identifier for locking
            operation: The async operation to perform
            refresh_func: Function to refresh the token
            max_retries: Maximum number of refresh retries

        Returns:
            Result of the operation

        Raises:
            SpotifyAuthError: If refresh fails or max retries exceeded
        """
        # Use per-user lock to prevent concurrent refresh attempts
        if user_id not in self._refreshing:
            self._refreshing[user_id] = asyncio.Lock()

        lock = self._refreshing[user_id]

        async with lock:
            for attempt in range(max_retries + 1):
                try:
                    return await operation()
                except SpotifyAuthError as e:
                    if "401" in str(e) or "auth" in str(e).lower():
                        if attempt < max_retries:
                            logger.info(f"Token expired for user {user_id}, refreshing...")
                            try:
                                await refresh_func()
                                continue  # Retry the operation with new token
                            except Exception as refresh_error:
                                logger.error(f"Token refresh failed for user {user_id}: {refresh_error}")
                                raise SpotifyAuthError(f"Token refresh failed: {refresh_error}")
                        else:
                            logger.error(f"Max retries exceeded for user {user_id}")
                            raise SpotifyAuthError("Authentication failed after refresh attempts")
                    else:
                        # Non-401 error, re-raise immediately
                        raise

        # This should never be reached
        raise SpotifyAuthError("Unexpected error in refresh helper")


class SpotifyRefreshHelper:
    """Spotify-specific refresh helper."""

    def __init__(self):
        self.generic_helper = RefreshHelper()
        self._last_refresh: dict[str, float] = {}

    async def refresh_spotify_token(self, user_id: str) -> None:
        """
        Refresh Spotify access token for a user.

        Args:
            user_id: User identifier

        Raises:
            SpotifyAuthError: If refresh fails
        """
        # Rate limit refreshes to prevent excessive API calls
        now = time.time()
        if user_id in self._last_refresh:
            time_since_last_refresh = now - self._last_refresh[user_id]
            if time_since_last_refresh < 30.0:  # Minimum 30 seconds between refreshes
                logger.warning(f"Rate limiting refresh for user {user_id}")
                await asyncio.sleep(30.0 - time_since_last_refresh)

        try:
            client = SpotifyClient(user_id)
            await client._refresh_tokens()
            self._last_refresh[user_id] = time.time()
            logger.info(f"Successfully refreshed Spotify token for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to refresh Spotify token for user {user_id}: {e}")
            raise SpotifyAuthError(f"Token refresh failed: {e}")

    async def execute_with_refresh(
        self,
        user_id: str,
        operation: Callable[[], Awaitable[Any]]
    ) -> Any:
        """
        Execute a Spotify operation with automatic token refresh on 401 errors.

        Args:
            user_id: User identifier
            operation: Async operation to perform

        Returns:
            Result of the operation
        """
        return await self.generic_helper.refresh_if_401(
            user_id=user_id,
            operation=operation,
            refresh_func=lambda: self.refresh_spotify_token(user_id)
        )


# Global instance for use across the application
spotify_refresh_helper = SpotifyRefreshHelper()


# Convenience function for easy use
async def refresh_if_401_spotify(
    user_id: str,
    operation: Callable[[], Awaitable[Any]]
) -> Any:
    """
    Convenience function to execute Spotify operations with automatic refresh.

    Args:
        user_id: User identifier
        operation: Async operation to perform

    Returns:
        Result of the operation
    """
    return await spotify_refresh_helper.execute_with_refresh(user_id, operation)
