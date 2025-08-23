from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["auth"], include_in_schema=False)

# LEGACY ROUTES REMOVED - Canonical Google OAuth routes are now in app/api/google_oauth.py
# This file is kept for potential future use but all OAuth routes have been moved to the canonical location

__all__ = ["router"]
