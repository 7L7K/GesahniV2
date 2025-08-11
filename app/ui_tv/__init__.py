"""
Granny Mode TV UI package.

This package contains the TV-first interface scaffolding:
- screens: high-level views (Home, Listening, Confirmation, Onboarding, Settings, Help)
- widgets: reusable UI pieces (CaptionBar, Yes/No bar, BigButtons, TileGrid, MediaPlayer overlay)
- state: UI store for voice status, onboarding progress, consent flags, and DND window

Note: This is the backend representation and structure map. The actual visual UI is scaffolded
in the Next.js frontend under `frontend/src/app/tv` and `frontend/src/components/tv`.
"""

__all__ = [
    "screens",
    "widgets",
    "state",
]


