from __future__ import annotations

import os

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "")

# space-separated - basic scopes for Spotify integration
_SCOPES_DEFAULT = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "playlist-modify-public "
    "playlist-modify-private "
    "user-library-modify"
)


def get_spotify_scopes() -> list[str]:
    """Return Spotify OAuth scopes from env or sensible defaults.

    Includes:
    - user-read-playback-state: Read current playback state
    - user-modify-playback-state: Control playback
    - user-read-currently-playing: Read currently playing track
    - playlist-modify-public: Modify public playlists
    - playlist-modify-private: Modify private playlists
    - user-library-modify: Modify user's library

    Override with SPOTIFY_SCOPES env var to customize permissions.
    """
    return os.getenv("SPOTIFY_SCOPES", _SCOPES_DEFAULT).split()


# JWT state secret for Spotify OAuth (reuse Google secret or use dedicated one)
JWT_STATE_SECRET = os.getenv("JWT_STATE_SECRET") or os.getenv("SPOTIFY_JWT_STATE_SECRET", "")
