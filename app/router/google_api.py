"""Google OAuth API routes for the router.

This module defines /v1/google/auth/* routes.
Leaf module - no imports from app/router/__init__.py.
"""
import hashlib
import hmac
import logging
from app import settings
import random
import secrets
import time
import base64
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import cookie_config as cookie_cfg
from app.integrations.google.config import JWT_STATE_SECRET
from app.integrations.google.state import (
    generate_signed_state,
    verify_signed_state,
    generate_pkce_verifier,
    generate_pkce_challenge,
)
from app.logging_config import req_id_var
from app.security import jwt_decode
from app.error_envelope import raise_enveloped

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(tags=["Auth"])


# Simple in-memory monitor for OAuth callback failures and clock skew alerts
from collections import deque


class OAuthCallbackMonitor:
    def __init__(self, window_seconds: float = 60.0):
        self.window = float(window_seconds)
        self.total = deque()
        self.failures = deque()

    def record(self, success: bool, ts: float | None = None) -> None:
        now = ts if ts is not None else time.time()
        cutoff = now - self.window
        self.total.append(now)
        if not success:
            self.failures.append(now)

        # Clean old entries
        while self.total and self.total[0] < cutoff:
            self.total.popleft()
        while self.failures and self.failures[0] < cutoff:
            self.failures.popleft()

    def failure_rate(self) -> float:
        if not self.total:
            return 0.0
        return len(self.failures) / len(self.total)


# Global monitor instance
# Global singleton moved to app/infra/oauth_monitor.py
# Use infra.get_oauth_monitor() instead


@router.get("/auth/login_url")
async def google_login_url(request: Request):
    """Generate Google OAuth login URL with CSRF protection."""
    try:
        # Generate OAuth state for CSRF protection
        state = generate_signed_state()

        # Generate PKCE verifier and challenge
        verifier = generate_pkce_verifier()
        challenge = generate_pkce_challenge(verifier)

        # Build OAuth URL
        params = {
            "client_id": settings.google_client_id(),
            "redirect_uri": settings.google_redirect_uri(),
            "scope": "openid email profile",
            "response_type": "code",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }

        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        # Store PKCE verifier in session/state for later retrieval
        # This would need to be implemented based on your session management

        return {
            "login_url": auth_url,
            "state": state,
        }

    except Exception as e:
        logger.error("google_login_url.failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate login URL")


@router.get("/auth/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Handle Google OAuth callback."""
    try:
        # Handle OAuth errors
        if error:
            logger.warning("google_oauth_callback.error", extra={"error": error, "state": state})
            raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code")

        if not state:
            raise HTTPException(status_code=400, detail="Missing state parameter")

        # Verify state for CSRF protection
        try:
            verify_signed_state(state)
        except Exception as e:
            logger.warning("google_oauth_callback.csrf", extra={"error": str(e)})
            raise HTTPException(status_code=403, detail="Invalid state parameter")

        # Record callback attempt
        from ..infra.oauth_monitor import get_oauth_monitor
        get_oauth_monitor().record_attempt(state)

        # Exchange code for tokens
        # This would need to be implemented based on your token exchange logic

        return {
            "status": "callback_received",
            "code": code[:10] + "...",  # Partial for logging
            "state": state,
            "note": "Token exchange not yet implemented in leaf module",
        }

    except HTTPException:
        get_oauth_monitor().record_attempt(state)
        raise
    except Exception as e:
        get_oauth_monitor().record_attempt(state)
        logger.error("google_oauth_callback.failed", exc_info=True)
        raise HTTPException(status_code=500, detail="OAuth callback failed")


@router.get("/google/oauth/callback", include_in_schema=False)
async def legacy_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Legacy Google OAuth callback endpoint."""
    # This is a compatibility endpoint
    return await google_oauth_callback(request, code, state, error)
