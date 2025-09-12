"""Authentication constants for GesahniV2.

Centralized definitions for cookie names, JWT settings, and auth-related constants.
All auth-related code should import from this module instead of using hardcoded values.
"""

import os

# Cookie names - standardized across the application
ACCESS_COOKIE = "gs_access"
REFRESH_COOKIE = "gs_refresh"
CSRF_COOKIE = "gs_csrf"

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET") or "test-jwt-secret-key-for-testing-only"
JWT_ALG = "HS256"
JWT_ISS = "gesahni"
JWT_AUD = "gesahni-users"

# CSRF header name (remains consistent)
CSRF_HEADER = "X-CSRF-Token"

# Session cookie (for additional session tracking)
SESSION_COOKIE = "gs_session"
