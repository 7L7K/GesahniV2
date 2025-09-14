"""
API router initialization and tag annotations for GesahniV2.

This module provides tag annotations for all API routers to ensure proper
OpenAPI documentation grouping.
"""

# Tag definitions for consistent grouping
TAGS = {
    "Care": "Care features, contacts, sessions, and Home Assistant actions.",
    "Music": "Music playback, voices, and TTS.",
    "Calendar": "Calendar and reminders.",
    "TV": "TV UI and related endpoints.",
    "Admin": "Admin, status, models, diagnostics, and tools.",
    "Auth": "Authentication and authorization.",
}

# Router tag mappings - maps router module paths to their tags
ROUTER_TAGS = {
    # Care-related routers
    "app.api.care": "Care",
    "app.api.care_ws": "Care",
    "app.api.contacts": "Care",
    "app.caregiver": "Care",
    # Music-related routers
    "app.api.music": "Music",
    "app.api.music_http": "Music",
    "app.api.music_ws": "Music",
    "app.api.tv_music_sim": "Music",
    "app.api.tts": "Music",  # TTS is part of Music functionality
    "app.api.voices": "Music",
    # Calendar-related routers
    "app.api.calendar": "Calendar",
    "app.api.reminders": "Calendar",
    # TV-related routers
    "app.api.tv": "TV",
    "app.api.photos": "TV",
    # Admin-related routers
    "app.api.admin": "Admin",
    "app.api.admin_ui": "Admin",
    "app.admin.routes": "Admin",
    "app.api.status": "Admin",
    "app.api.health": "Admin",
    "app.api.models": "Admin",
    "app.api.debug": "Admin",
    "app.api.core_misc": "Admin",
    "app.api.selftest": "Admin",
    "app.api.integrations_status": "Admin",
    "app.api.logs_simple": "Admin",
    "app.api.util": "Admin",
    "app.health": "Admin",
    # Auth-related routers
    "app.api.auth": "Auth",
    "app.api.auth_password": "Auth",
    "app.api.auth_router_dev": "Auth",
    "app.api.auth_router_pats": "Auth",
    "app.api.auth_router_refresh": "Auth",
    "app.api.auth_router_whoami": "Auth",
    "app.api.google_oauth": "Auth",
    "app.api.oauth_apple": "Auth",
    "app.api.oauth_apple_stub": "Auth",
    "app.api.profile": "Auth",
    "app.api.me": "Auth",
    "app.auth": "Auth",
    "app.auth_device": "Auth",
    # Other routers (may need reassignment based on functionality)
    "app.api.capture": "Admin",  # Could be Care or Admin depending on use case
    "app.api.sessions_http": "Admin",
    "app.api.sessions_ws": "Admin",
    "app.api.transcribe": "Admin",
    "app.api.ha_local": "Care",  # Home Assistant actions
    "app.api.memories": "Admin",
    "app.api.well_known": "Admin",
    "app.api.google_services": "Admin",
    "app.api.health_google": "Admin",
    "app.api.devices": "Admin",
    "app.api.spotify_sdk": "Music",
    "app.api.spotify": "Music",
    "app.api.spotify_player": "Music",
    "app.api.schema": "Admin",
    "app.api.preflight": "Admin",
    "app.integrations.google.routes": "Admin",
}


def get_router_tag(router_module: str) -> str:
    """
    Get the appropriate tag for a router module.

    Args:
        router_module: The module path of the router (e.g., "app.api.care")

    Returns:
        The tag name for this router
    """
    return ROUTER_TAGS.get(router_module, "Admin")  # Default to Admin if not found
