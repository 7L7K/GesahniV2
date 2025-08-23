# app/auth_providers.py
"""
Environment-based feature flags for route inclusion and authentication providers.

This module provides centralized control over which routes and features are
available based on environment configuration, following the principle of
"honest codes" - if a feature is disabled, the routes truly don't exist.
"""

import os
from typing import Any


def admin_enabled() -> bool:
    """
    Determine if admin routes should be mounted based on environment.

    Returns True if admin routes should be available, False if they should be hidden.
    When disabled, admin routes will not exist (404) rather than return 401/403.

    Logic:
    - In production: Only enable if explicitly set via ENABLE_ADMIN_ROUTES
    - In non-production: Always enable for development/testing convenience
    """
    env = os.getenv("ENV", "dev").lower()

    # In production, require explicit opt-in
    if env == "prod":
        return os.getenv("ENABLE_ADMIN_ROUTES", "1").lower() in {"1", "true", "yes", "on"}

    # In dev/staging/test, always enable for convenience
    return True


def apple_oauth_enabled() -> bool:
    """
    Determine if Apple OAuth routes should be mounted.

    Similar logic to admin_enabled() - provides environment-based control
    over OAuth provider availability.
    """
    env = os.getenv("ENV", "dev").lower()

    # In production, require credentials to be configured
    if env == "prod":
        return bool(os.getenv("APPLE_CLIENT_ID") and os.getenv("APPLE_CLIENT_SECRET"))

    # In non-production, enable by default
    return os.getenv("ENABLE_APPLE_OAUTH", "1").lower() in {"1", "true", "yes", "on"}


def get_enabled_features() -> dict[str, bool]:
    """
    Get a summary of all environment-based feature flags.

    Useful for debugging and system status endpoints.
    """
    return {
        "admin_routes": admin_enabled(),
        "apple_oauth": apple_oauth_enabled(),
        "environment": os.getenv("ENV", "dev"),
    }


def feature_status() -> dict[str, Any]:
    """
    Get detailed feature status for debugging and monitoring.

    Includes both boolean flags and environment variable values.
    """
    return {
        "features": get_enabled_features(),
        "env_vars": {
            "ENV": os.getenv("ENV", "dev"),
            "ENABLE_ADMIN_ROUTES": os.getenv("ENABLE_ADMIN_ROUTES"),
            "ENABLE_APPLE_OAUTH": os.getenv("ENABLE_APPLE_OAUTH"),
            "APPLE_CLIENT_ID": bool(os.getenv("APPLE_CLIENT_ID")),
            "APPLE_CLIENT_SECRET": bool(os.getenv("APPLE_CLIENT_SECRET")),
        }
    }