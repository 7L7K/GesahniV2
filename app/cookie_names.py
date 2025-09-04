"""Canonical cookie name constants and legacy mappings.

Use these constants as a single source of truth for cookie names.
Writes MUST use the GSNH_* names. During reads we accept legacy names and
immediately rewrite them using the new names.
"""

# Canonical cookie names (single source of truth)
# Use contract-stable lowercase names for cookies that will be frozen in contracts.
# Keep legacy constants for compatibility elsewhere in the codebase.
GSNH_AT = "gsn_access"  # access token (canonical)
GSNH_RT = "gsn_refresh"  # refresh token (canonical)
GSNH_SESS = "gsn_session"  # opaque app session id

# Backward-compatible canonical constants expected by other modules.
# These map to the standard cookie names used across the app.
ACCESS_TOKEN = "access_token"
REFRESH_TOKEN = "refresh_token"
SESSION = "__session"

# Legacy names supported during migration (abstract names for test compatibility)
ACCESS_TOKEN_LEGACY = "access_token"
REFRESH_TOKEN_LEGACY = "refresh_token"
SESSION_LEGACY = "__session"

__all__ = [
    "GSNH_AT",
    "GSNH_RT",
    "GSNH_SESS",
    "ACCESS_TOKEN",
    "REFRESH_TOKEN",
    "SESSION",
    "ACCESS_TOKEN_LEGACY",
    "REFRESH_TOKEN_LEGACY",
    "SESSION_LEGACY",
]
