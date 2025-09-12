"""Legacy auth router - not currently used.

Legacy routes are now handled directly in app.api.auth with include_in_schema=False.
This router is kept for potential future use if redirects are needed.
"""
from fastapi import APIRouter

router = APIRouter()
# Empty router - legacy routes are handled in app.api.auth
