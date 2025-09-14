# app/settings_rate.py
"""
Rate limiting configuration settings.

This module centralizes all rate limit configuration to ensure consistent
behavior across the application and proper environment variable handling.
"""

import os


class RateLimitSettings:
    """Rate limiting configuration with dynamic environment variable support."""

    def __init__(self):
        self._cache = {}

    def _get_env_int(self, key: str, default: str | int) -> int:
        """Get integer value from environment with caching."""
        if key not in self._cache:
            env_value = os.getenv(key)
            if env_value is not None:
                try:
                    self._cache[key] = int(env_value)
                except ValueError:
                    self._cache[key] = (
                        int(default) if isinstance(default, str) else default
                    )
            else:
                self._cache[key] = int(default) if isinstance(default, str) else default
        return self._cache[key]

    def _get_env_float(self, key: str, default: str | float) -> float:
        """Get float value from environment with caching."""
        if key not in self._cache:
            env_value = os.getenv(key)
            if env_value is not None:
                try:
                    self._cache[key] = float(env_value)
                except ValueError:
                    self._cache[key] = (
                        float(default) if isinstance(default, str) else default
                    )
            else:
                self._cache[key] = (
                    float(default) if isinstance(default, str) else default
                )
        return self._cache[key]

    def _get_env_str(self, key: str, default: str) -> str:
        """Get string value from environment with caching."""
        if key not in self._cache:
            env_value = os.getenv(key, default)
            self._cache[key] = env_value.strip() if env_value else default
        return self._cache[key]

    def _get_env_set(self, key: str, default: str = "") -> set[str]:
        """Get set of strings from comma-separated environment variable."""
        if key not in self._cache:
            env_value = os.getenv(key, default)
            if env_value:
                self._cache[key] = set(
                    s.strip() for s in env_value.split(",") if s.strip()
                )
            else:
                self._cache[key] = set()
        return self._cache[key]

    def clear_cache(self):
        """Clear cached values - useful for testing."""
        self._cache.clear()

    def set_test_config(self, **kwargs):
        """Set test configuration values - for testing only."""
        for key, value in kwargs.items():
            self._cache[key] = value

    def reset_test_config(self):
        """Reset test configuration to environment defaults."""
        self.clear_cache()

    @property
    def rate_limit_per_min(self) -> int:
        """Maximum requests per minute."""
        return self._get_env_int("RATE_LIMIT_PER_MIN", 60)

    @property
    def rate_limit_burst(self) -> int:
        """Burst limit for rate limiting."""
        return self._get_env_int("RATE_LIMIT_BURST", 10)

    @property
    def window_seconds(self) -> int:
        """Rate limit window in seconds."""
        return self._get_env_int("RATE_LIMIT_WINDOW_S", 60)

    @property
    def burst_window_seconds(self) -> float:
        """Burst rate limit window in seconds."""
        return self._get_env_float("RATE_LIMIT_BURST_WINDOW_S", 60)

    @property
    def bypass_scopes(self) -> set[str]:
        """Set of scopes that bypass rate limiting."""
        return self._get_env_set("RATE_LIMIT_BYPASS_SCOPES", "")

    @property
    def key_scope(self) -> str:
        """Scope for rate limit keys (global, user, ip, route)."""
        return self._get_env_str("RATE_LIMIT_KEY_SCOPE", "global").lower()

    @property
    def backend(self) -> str:
        """Rate limit backend (memory, redis, distributed)."""
        return self._get_env_str("RATE_LIMIT_BACKEND", "memory").lower()

    @property
    def redis_prefix(self) -> str:
        """Redis prefix for rate limit keys."""
        return self._get_env_str("RATE_LIMIT_REDIS_PREFIX", "rl").strip(":")


# Global instance for application use
rate_limit_settings = RateLimitSettings()
