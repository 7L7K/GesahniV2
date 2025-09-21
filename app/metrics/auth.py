"""Authentication-specific Prometheus metrics."""

from . import Counter

AUTH_LEGACY_SHIM_TOTAL = Counter(
    "auth_legacy_shim_total",
    "Hits to legacy auth routes",
    ["path"],
)

AUTH_REFRESH_ROTATIONS_TOTAL = Counter(
    "auth_refresh_rotations_total",
    "Successful refresh rotations",
)

AUTH_OAUTH_CALLBACK_TOTAL = Counter(
    "auth_oauth_callback_total",
    "OAuth callback results",
    ["provider", "result"],
)

__all__ = [
    "AUTH_LEGACY_SHIM_TOTAL",
    "AUTH_REFRESH_ROTATIONS_TOTAL",
    "AUTH_OAUTH_CALLBACK_TOTAL",
]
