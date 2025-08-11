from __future__ import annotations
import os
from typing import List

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/google/oauth/callback")

# space-separated
_SCOPES_DEFAULT = (
    "openid https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar.events"
)

def get_google_scopes() -> List[str]:
    """Return Google OAuth scopes from env or sensible defaults.

    Uses userinfo.* scopes to align with Google's token response and avoid
    oauthlib "scope_changed" warnings.
    """
    return os.getenv("GOOGLE_SCOPES", _SCOPES_DEFAULT).split()

# used to sign our state param
JWT_STATE_SECRET = os.getenv("JWT_STATE_SECRET", "dev_only_change_me")

# optional: override DB URL; defaults to sqlite file
GOOGLE_OAUTH_DB_URL = os.getenv("GOOGLE_OAUTH_DB_URL", "sqlite:///./google_oauth.sqlite3")

def validate_config():
    missing = []
    if not GOOGLE_CLIENT_ID: missing.append("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_SECRET: missing.append("GOOGLE_CLIENT_SECRET")
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
