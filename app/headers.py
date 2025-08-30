# app/headers.py
"""
Standardized header utilities for consistent casing and rate limit headers.

This module provides utilities for standardizing HTTP header names and values,
particularly for rate limiting headers that must follow RFC 6585 and RFC 7231.
"""

import time
from typing import Dict, Any


class HeaderUtils:
    """Utilities for standardizing HTTP headers."""

    @staticmethod
    def standardize_headers(headers: Dict[str, Any]) -> Dict[str, str]:
        """Convert all header values to strings and ensure proper casing."""
        standardized = {}
        for key, value in headers.items():
            # Convert key to title case (e.g., "rate-limit" -> "Rate-Limit")
            standardized_key = "-".join(word.capitalize() for word in key.split("-"))

            # Convert value to string
            if isinstance(value, str):
                standardized_value = value
            elif isinstance(value, (int, float)):
                standardized_value = str(int(value) if isinstance(value, float) and value.is_integer() else value)
            elif value is None:
                standardized_value = ""
            else:
                standardized_value = str(value)

            standardized[standardized_key] = standardized_value

        return standardized

    @staticmethod
    def create_rate_limit_headers(
        limit: int,
        remaining: int,
        reset_time: int,
        retry_after: int | None = None
    ) -> Dict[str, str]:
        """Create standardized rate limit headers per RFC 6585."""
        headers = {
            "rate-limit-limit": limit,
            "rate-limit-remaining": remaining,
            "rate-limit-reset": reset_time,
        }

        if retry_after is not None:
            headers["retry-after"] = retry_after

        return HeaderUtils.standardize_headers(headers)

    @staticmethod
    def create_rate_limit_response_headers(
        limit: int,
        remaining: int,
        window_seconds: int
    ) -> Dict[str, str]:
        """Create rate limit headers for successful responses."""
        reset_time = int(time.time()) + window_seconds
        return HeaderUtils.create_rate_limit_headers(limit, remaining, reset_time)


# Convenience functions for common use cases
def get_rate_limit_headers(limit: int, remaining: int, window_seconds: int) -> Dict[str, str]:
    """Get standardized rate limit headers for a response."""
    return HeaderUtils.create_rate_limit_response_headers(limit, remaining, window_seconds)


def get_retry_after_header(seconds: int) -> Dict[str, str]:
    """Get retry-after header for rate limited responses."""
    return HeaderUtils.standardize_headers({"retry-after": seconds})
