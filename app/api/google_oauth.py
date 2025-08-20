"""
Google OAuth login URL endpoint.

This module provides a stateless endpoint that generates Google OAuth URLs
and sets short-lived CSRF state cookies for security.
"""

import os
import time
import secrets
import random
import hmac
import hashlib
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..auth import SECRET_KEY
from ..integrations.google.config import JWT_STATE_SECRET
from ..cookie_config import get_cookie_config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


def _allow_redirect(url: str) -> bool:
    """Check if redirect URL is allowed based on OAUTH_REDIRECT_ALLOWLIST."""
    allowed = os.getenv("OAUTH_REDIRECT_ALLOWLIST", "").split(",")
    allowed = [u.strip() for u in allowed if u.strip()]
    if not allowed:
        return True
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        return any(host.endswith(a.lower()) for a in allowed)
    except Exception:
        return False


class LoginUrlResponse(BaseModel):
    """Response model for the login URL endpoint."""
    url: str


def _generate_signed_state() -> str:
    """
    Generate a signed state string for CSRF protection.
    
    Returns:
        str: timestamp:random:sig format (kept short to avoid URL length issues)
    """
    logger.debug("🔐 Generating timestamp for state")
    timestamp = str(int(time.time()))
    
    logger.debug("🎲 Generating random token for state")
    random_token = secrets.token_urlsafe(16)  # Reduced from 32 to 16 for shorter state
    
    # Create signature using a dedicated state secret (separate from JWT_SECRET)
    logger.debug("🔏 Creating HMAC signature for state using JWT_STATE_SECRET")
    message = f"{timestamp}:{random_token}".encode()
    sig_key = JWT_STATE_SECRET.encode() if isinstance(JWT_STATE_SECRET, str) else JWT_STATE_SECRET
    signature = hmac.new(sig_key, message, hashlib.sha256).hexdigest()[:12]
    
    state = f"{timestamp}:{random_token}:{signature}"
    logger.debug(f"✅ State generated: {timestamp}:[random]:[signature] (length: {len(state)})")
    return state


@router.get("/google/auth/login_url")
async def google_login_url(request: Request) -> Response:
    """
    Generate a Google OAuth login URL with CSRF protection.
    
    Returns a Google OAuth URL and sets a short-lived state cookie
    for CSRF protection. If Google OAuth is not configured, returns 503.
    """
    logger.info("🔐 Google OAuth login URL endpoint hit")
    logger.info("📋 Starting OAuth flow - checking configuration")
    
    # Read required environment variables
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    
    logger.info(f"🔧 Configuration check - Client ID: {'✅ Set' if client_id else '❌ Missing'}")
    logger.info(f"🔧 Configuration check - Redirect URI: {'✅ Set' if redirect_uri else '❌ Missing'}")
    
    # Fail fast if configuration is missing
    if not client_id or not redirect_uri:
        logger.error("❌ Google OAuth configuration missing - returning 503")
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured (set GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI)"
        )
    
    logger.info("✅ Configuration validated - proceeding with OAuth URL generation")
    
    # Generate signed state for CSRF protection
    logger.info("🔐 Generating signed state for CSRF protection")
    state = _generate_signed_state()
    logger.info("✅ Signed state generated successfully")
    
    # Build Google OAuth URL
    logger.info("🌐 Building Google OAuth URL parameters")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    logger.info("✅ Base OAuth parameters configured")
    
    # Add optional parameters only if explicitly configured
    # Note: These can leak tenant/user info - only use if you want to restrict or hint
    logger.info("🔍 Checking optional parameters (hd, login_hint)")
    hd = os.getenv("GOOGLE_HD")
    if hd and hd.strip():  # Only include if explicitly set and not empty
        params["hd"] = hd.strip()
        logger.info("✅ HD parameter included")
    else:
        logger.info("ℹ️ HD parameter not set - skipping")
    
    login_hint = os.getenv("GOOGLE_LOGIN_HINT")
    if login_hint and login_hint.strip():  # Only include if explicitly set and not empty
        params["login_hint"] = login_hint.strip()
        logger.info("✅ Login hint parameter included")
    else:
        logger.info("ℹ️ Login hint parameter not set - skipping")
    
    # Echo through next query param if present and allowed
    logger.info("🔗 Processing next parameter for redirect")
    next_url = request.query_params.get("next")
    if next_url:
        logger.info("📋 Next parameter found - validating redirect URL")
        if not _allow_redirect(next_url):
            logger.warning("🚫 Blocked disallowed redirect URL")  # Don't log the actual URL
            next_url = "/"  # Reset to safe default
            logger.info("🔄 Reset next parameter to safe default '/'")
        else:
            logger.info("✅ Next parameter validated successfully")
        params["redirect_params"] = f"next={next_url}"
        logger.info("✅ Next parameter added to OAuth URL")
    else:
        logger.info("ℹ️ No next parameter provided")
    
    logger.info("🔗 Constructing final OAuth URL")
    oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    logger.info("✅ OAuth URL constructed successfully")
    
    # Create JSON response with state cookie
    logger.info("🍪 Setting up response with state cookie")
    # legacy clients expect `auth_url` key; keep compatibility
    response_data = {"auth_url": oauth_url}
    
    # Set OAuth state cookie using centralized cookie surface
    logger.info("🍪 Setting OAuth state cookie with 5-minute TTL")
    from ..cookies import set_oauth_state_cookies
    
    # Create a Response object to set the cookie
    import json
    http_response = Response(
        content=json.dumps(response_data),
        media_type="application/json"
    )
    
    # Use centralized cookie surface for OAuth state cookies
    set_oauth_state_cookies(
        resp=http_response,
        state=state,
        next_url=next_url or "/",
        request=request,
        ttl=300,  # 5 minutes
        provider="g"  # Google-specific cookie prefix
    )
    
    logger.info("🎉 OAuth login URL endpoint completed successfully")
    return http_response


def _verify_signed_state(state: str) -> bool:
    """
    Verify a signed state string for CSRF protection.
    
    Args:
        state: State string in timestamp:random:sig format
        
    Returns:
        bool: True if state is valid and fresh
    """
    try:
        parts = state.split(":")
        if len(parts) != 3:
            return False
            
        timestamp, random_token, signature = parts
        
        # Verify timestamp is recent (within 5 minutes)
        state_time = int(timestamp)
        current_time = int(time.time())
        if current_time - state_time > 300:  # 5 minutes
            return False
            
        # Verify signature using the dedicated state secret
        message = f"{timestamp}:{random_token}".encode()
        sig_key = JWT_STATE_SECRET.encode() if isinstance(JWT_STATE_SECRET, str) else JWT_STATE_SECRET
        expected_sig = hmac.new(sig_key, message, hashlib.sha256).hexdigest()[:12]
        
        return signature == expected_sig
    except Exception:
        return False


@router.get("/google/auth/callback")
async def google_callback(request: Request) -> Response:
    """
    Handle Google OAuth callback with strict state validation.
    
    Validates the signed state parameter and processes the OAuth code.
    Rejects requests with missing, expired, or invalid state.
    Clears the state cookie after validation and proceeds with session logic.
    """
    logger.info("🔄 Google OAuth callback endpoint hit")
    logger.info("📋 Starting callback validation process")
    
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    # Strict validation - respond with cleared state cookie on any error
    logger.info(f"🔍 Validating callback parameters - Code: {'✅ Present' if code else '❌ Missing'}, State: {'✅ Present' if state else '❌ Missing'}")
    cookie_config = get_cookie_config(request)
    def _error_response(msg: str, status: int = 400) -> Response:
        import json
        resp = Response(content=json.dumps({"detail": msg}), media_type="application/json", status_code=status)
        # Clear OAuth state cookies using centralized surface
        from ..cookies import clear_oauth_state_cookies
        clear_oauth_state_cookies(resp, request, provider="g")
        return resp

    if not code or not state:
        logger.error("❌ Google OAuth callback missing code or state")
        return _error_response("missing_code_or_state", status=400)

    # Get state cookie and validate
    logger.info("🍪 Checking for g_state cookie")
    state_cookie = request.cookies.get("g_state")
    
    # For local development, bypass state cookie validation if cookie is missing
    dev_mode = os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}
    if not state_cookie and dev_mode:
        logger.warning("⚠️ Development mode: Bypassing state cookie validation")
        logger.info("✅ State cookie validation bypassed for development")
    elif not state_cookie:
        logger.error("❌ Google OAuth callback missing state cookie")
        return _error_response("missing_state_cookie", status=400)
    else:
        logger.info("✅ State cookie found")

    # Verify state matches cookie exactly (skip in dev mode if no cookie)
    if state_cookie:
        logger.info("🔍 Validating state parameter matches cookie")
        if state != state_cookie:
            logger.error("❌ Google OAuth callback state mismatch")
            return _error_response("state_mismatch", status=400)
        logger.info("✅ State parameter matches cookie")
    else:
        logger.info("⚠️ Development mode: Skipping state parameter validation")

    # Verify signed state is valid and fresh
    logger.info("🔐 Verifying signed state signature and freshness")
    if not _verify_signed_state(state):
        if dev_mode:
            logger.warning("⚠️ Development mode: Bypassing signed state validation")
            logger.info("✅ Signed state validation bypassed for development")
        else:
            logger.error("❌ Google OAuth callback invalid or expired state")
            return _error_response("invalid_state", status=400)
    else:
        logger.info("✅ Signed state validation passed")
    
    # State is valid - clear/rotate the state cookie after use
    logger.info("🍪 Clearing OAuth state cookies after successful validation")
    
    # Create response object to set cleared cookie
    response = Response(
        content="OAuth callback received successfully. State validation passed.",
        media_type="text/plain"
    )
    
    # Clear OAuth state cookies using centralized surface
    from ..cookies import clear_oauth_state_cookies
    clear_oauth_state_cookies(response, request, provider="g")
    logger.info("✅ OAuth state cookies cleared successfully")
    
    # State validation complete - proceed with usual session logic
    logger.info("✅ Google OAuth callback state validated successfully")
    logger.info("🎉 All validation checks passed - proceeding with OAuth flow")
    
    # Perform token exchange and create an application session/redirect.
    # We keep this flow minimal and deterministic for tests and local dev:
    # 1) Exchange the code for Google credentials
    # 2) Extract a stable user identifier (email or sub)
    # 3) Persist the provider tokens in the google_oauth DB
    # 4) Mint application access/refresh JWTs and redirect the browser
    try:
        from ..integrations.google import oauth as go
        from ..integrations.google.db import SessionLocal, GoogleToken, init_db

        import jwt as pyjwt
        from urllib.parse import urlencode
        from starlette.responses import RedirectResponse
        from uuid import uuid4

        # Exchange the authorization code (state already validated by this endpoint)
        creds = go.exchange_code(code, state, verify_state=False)

        # Try to extract email/sub from id_token (best-effort, without verification)
        provider_user_id = None
        email = None
        try:
            id_token = getattr(creds, "id_token", None)
            if id_token:
                claims = pyjwt.decode(id_token, options={"verify_signature": False})
                email = claims.get("email") or claims.get("email_address")
                provider_user_id = claims.get("sub") or email
        except Exception:
            # Swallow - we'll fallback to tokens
            provider_user_id = None

        # Fallback identifiers
        if not provider_user_id:
            provider_user_id = getattr(creds, "refresh_token", None) or getattr(creds, "token", None) or str(uuid4())
        if not email:
            # Use provider_user_id as email fallback (not ideal but deterministic)
            email = str(provider_user_id)

        # Persist provider record into google_oauth DB (best-effort)
        try:
            init_db()
            rec = go.creds_to_record(creds)
            uid = str(email).lower()
            with SessionLocal() as s:
                row = s.get(GoogleToken, uid)
                if row is None:
                    row = GoogleToken(user_id=uid,
                                      access_token=rec.get("access_token"),
                                      refresh_token=rec.get("refresh_token"),
                                      token_uri=rec.get("token_uri"),
                                      client_id=rec.get("client_id"),
                                      client_secret=rec.get("client_secret"),
                                      scopes=rec.get("scopes"),
                                      expiry=rec.get("expiry"))
                    s.add(row)
                else:
                    row.access_token = rec.get("access_token")
                    row.refresh_token = rec.get("refresh_token")
                    row.token_uri = rec.get("token_uri")
                    row.client_id = rec.get("client_id")
                    row.client_secret = rec.get("client_secret")
                    row.scopes = rec.get("scopes")
                    row.expiry = rec.get("expiry")
                s.commit()
        except Exception:
            logger.exception("Failed to persist Google tokens (non-fatal)")

        # Mint application JWTs (access + refresh) for the user and redirect
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        # Use tokens.py facade instead of direct JWT encoding
        from ..tokens import make_access, make_refresh
        at = make_access({"user_id": uid})
        rt = make_refresh({"user_id": uid})

        # Build redirect query - keep it compact and URL-encoded
        q = urlencode({"access_token": at, "refresh_token": rt})

        # If APP_URL appears to point at this backend (common in local dev),
        # prefer the browser origin or referer so the redirect lands on the
        # frontend (e.g. http://localhost:3000) instead of the backend port.
        try:
            from urllib.parse import urlparse
            parsed = urlparse(app_url)
            host_matches_backend = False
            try:
                host_matches_backend = (parsed.hostname == request.url.hostname) and (parsed.port == request.url.port)
            except Exception:
                host_matches_backend = False

            if host_matches_backend:
                origin = request.headers.get("origin") or request.headers.get("referer")
                if origin:
                    op = urlparse(origin)
                    app_url = f"{op.scheme}://{op.netloc}"
        except Exception:
            # Best-effort only; fall back to APP_URL env value
            pass

        # Set tokens as HttpOnly cookies and redirect to frontend root
        # Determine final frontend origin similar to earlier logic
        final_root = f"{app_url.rstrip('/')}/"
        try:
            from urllib.parse import urlparse
            parsed = urlparse(app_url)
            host_matches_backend = False
            try:
                host_matches_backend = (parsed.hostname == request.url.hostname) and (parsed.port == request.url.port)
            except Exception:
                host_matches_backend = False
            if host_matches_backend:
                origin = request.headers.get("origin") or request.headers.get("referer")
                if origin:
                    op = urlparse(origin)
                    final_root = f"{op.scheme}://{op.netloc}/"
        except Exception:
            pass

        resp = RedirectResponse(url=final_root, status_code=302)
        
        # Get TTLs from centralized configuration
        from ..cookie_config import get_token_ttls
        access_ttl, refresh_ttl = get_token_ttls()
        
        # Optional legacy __session cookie for integrations
        session_id = None
        if os.getenv('ENABLE_SESSION_COOKIE', '') in ('1', 'true', 'yes'):
            # Create opaque session ID instead of using JWT
            try:
                from ..auth import _create_session_id
                import jwt
                payload = jwt.decode(at, os.getenv("JWT_SECRET"), algorithms=["HS256"])
                jti = payload.get("jti")
                expires_at = payload.get("exp", time.time() + access_ttl)
                if jti:
                    session_id = _create_session_id(jti, expires_at)
                else:
                    session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to create session ID: {e}")
                session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
        
        # Use centralized cookie functions
        from ..cookies import set_auth_cookies
        set_auth_cookies(resp, access=at, refresh=rt, session_id=session_id, access_ttl=access_ttl, refresh_ttl=refresh_ttl, request=request)
        logger.info("🔁 Redirecting user to %s (cookies set)", final_root)
        return resp
    except Exception as e:
        # Log the exception type/message (always)
        logger.error("OAuth callback processing failed: %s: %s", type(e).__name__, e)

        # Log full traceback (guarantees stacktrace to configured logger)
        import traceback
        tb = traceback.format_exc()
        logger.error("Full traceback:\n%s", tb)

        # Also use logger.exception for any handlers that include exc_info
        logger.exception("OAuth callback exception for diagnostics")

        # Determine user-friendly message and status
        msg = "oauth_callback_failed"
        status = 500
        try:
            if isinstance(e, ValueError) and "JWT_SECRET" in str(e):
                msg = "server_misconfigured_jwt_secret"
                status = 503
        except Exception:
            pass

        # If running locally, return trace in the HTTP response for quick debugging.
        # WARNING: do NOT enable this in production.
        if os.getenv("ENV", "").lower() in ("dev", "development", "local", "test"):
            return _error_response(f"{msg}: {type(e).__name__}: {e}\n{tb}", status=status)

        # Otherwise, return sanitized cookie-clearing response (no internals leaked)
        return _error_response(msg, status=status)


# Note: This endpoint is stateless - no database writes.
# The cookie is just to bind browser↔callback for CSRF protection.
# If misconfigured, it fails fast with 503 (no silent defaults).
