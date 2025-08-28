"""External integrations scaffolding.

Subpackages live under `app/integrations/<provider>/` (e.g., `spotify`, `google`).
Home Assistant remains in `app/home_assistant.py`.
"""

__all__ = [
    "calendar_google",
    "calendar_apple",
    "music_apple",
    "photos_shared_album",
]
