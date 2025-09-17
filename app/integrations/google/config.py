from __future__ import annotations

import os

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

# space-separated - basic scopes for sign-in + optional Google services
_SCOPES_DEFAULT = (
    "openid https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/calendar.readonly"
)


def get_google_scopes() -> list[str]:
    """Return Google OAuth scopes from env or sensible defaults.

    Includes:
    - openid, email, profile: Basic sign-in and user identification
    - gmail.send: For sending emails via Gmail API
    - calendar.events: For creating calendar events via Google Calendar API

    Override with GOOGLE_SCOPES env var to customize permissions.
    Set to "openid email profile" for minimal scopes if Google services not needed.
    """
    return os.getenv("GOOGLE_SCOPES", _SCOPES_DEFAULT).split()


# used to sign our state param
JWT_STATE_SECRET = os.getenv("JWT_STATE_SECRET", "")

# optional: override DB URL; use main database URL if not specified
GOOGLE_OAUTH_DB_URL = os.getenv("GOOGLE_OAUTH_DB_URL", os.getenv("DATABASE_URL", ""))


def validate_config():
    missing = []
    if not GOOGLE_CLIENT_ID:
        missing.append("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_SECRET:
        missing.append("GOOGLE_CLIENT_SECRET")
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
