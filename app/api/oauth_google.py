from __future__ import annotations

import base64
import os
import time
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..sessions_store import sessions_store


router = APIRouter(tags=["auth"], include_in_schema=False)

# LEGACY ROUTES REMOVED - Canonical Google OAuth routes are now in app/api/google_oauth.py
# This file is kept for potential future use but all OAuth routes have been moved to the canonical location

__all__ = ["router"]


