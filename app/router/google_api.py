"""Google OAuth API routes for the router.

This module defines /v1/google/auth/* routes.
Leaf module - no imports from app/router/__init__.py.
"""
import logging
import time
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request

from app import settings
from app.integrations.google.state import (
    generate_pkce_challenge,
    generate_pkce_verifier,
    generate_signed_state,
    verify_signed_state,
)

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


def _get_oauth_monitor_safe():
    """Return the infra oauth monitor or None without creating local name binding

    Import inside the helper so callers can safely call this from anywhere in the
    module without causing UnboundLocalError when the import fails.
    """
    try:
        from ..infra.oauth_monitor import get_oauth_monitor

        try:
            return get_oauth_monitor()
        except Exception:
            return None
    except Exception:
        return None


@router.get("/login_url")
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

    except Exception:
        logger.error("google_login_url.failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate login URL")


@router.get("/callback")
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

        # Record callback attempt (best-effort)
        mon = _get_oauth_monitor_safe()
        if mon is not None and hasattr(mon, "record"):
            try:
                mon.record(success=True if error is None else False)
            except Exception:
                pass

        # Exchange code for tokens
        # This would need to be implemented based on your token exchange logic

        return {
            "status": "callback_received",
            "code": code[:10] + "...",  # Partial for logging
            "state": state,
            "note": "Token exchange not yet implemented in leaf module",
        }

    except HTTPException:
        mon = _get_oauth_monitor_safe()
        if mon is not None and hasattr(mon, "record_attempt"):
            try:
                mon.record_attempt(state)
            except Exception:
                pass
        raise
    except Exception:
        mon = _get_oauth_monitor_safe()
        if mon is not None and hasattr(mon, "record_attempt"):
            try:
                mon.record_attempt(state)
            except Exception:
                pass
        logger.error("google_oauth_callback.failed", exc_info=True)
        raise HTTPException(status_code=500, detail="OAuth callback failed")


@router.get("/connect")
async def google_connect(request: Request):
    """Compatibility endpoint: return authorize_url and set state cookie.

    Bridges to app.api.google_oauth.google_login_url, which sets the OAuth
    state cookie. Adapts the response body key to "authorize_url" expected by
    tests and legacy clients.
    """
    try:
        from app.api.google_oauth import google_login_url as _login
        # Call underlying handler to generate URL and state cookies
        resp = await _login(request)
        # Extract body safely
        data = {}
        try:
            import json
            data = json.loads(getattr(resp, "body", b"{}") or b"{}")
        except Exception:
            pass
        url = data.get("auth_url") or data.get("url") or data.get("login_url")
        from fastapi.responses import JSONResponse
        out = JSONResponse({"authorize_url": url} if url else {"authorize_url": ""})
        # Propagate Set-Cookie headers
        try:
            for k, v in resp.headers.items():
                if k.lower() == "set-cookie":
                    out.headers.append("set-cookie", v)
        except Exception:
            pass
        return out
    except HTTPException:
        raise
    except Exception:
        logger.exception("google_connect.failed")
        raise HTTPException(status_code=500, detail="failed_to_build_google_url")


@router.post("/callback")
async def google_oauth_callback_post(request: Request):
    """POST shim: redirect to canonical GET /v1/google/callback preserving query string."""
    qs = request.scope.get("query_string", b"").decode()
    target = "/v1/google/callback" + (f"?{qs}" if qs else "")
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=target, status_code=303)

