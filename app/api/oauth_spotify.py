from __future__ import annotations

import logging
import os
import time
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from ..web import cookies
from ..integrations.spotify.config import get_spotify_scopes
from ..integrations.spotify.state import (
    generate_pkce_challenge,
    generate_pkce_verifier,
    generate_signed_state,
)
from ..logging_config import req_id_var

logger = logging.getLogger(__name__)
# KILL-SWITCH DOCUMENTATION:
# ========================
# Canonical mount: /v1/auth/spotify
# Leaf routes only: /login_url, /callback
# No OAuth endpoints may live under /v1/spotify/*.
#
# This ensures clean separation between OAuth auth endpoints (/v1/auth/spotify/*)
# and integration endpoints (/v1/integrations/spotify/* or /v1/spotify/* for services).
#
# If adding shims/redirects, must be 308 permanent redirects and hidden from schema
# with include_in_schema=False.

router = APIRouter(tags=["auth"], include_in_schema=False)


@router.get("/login_url", name="spotify_oauth_login_url")
async def spotify_login_url(request: Request) -> Response:
    """Generate Spotify OAuth login URL with CSRF protection."""
    start_time = time.time()
    req_id = req_id_var.get()

    try:
        # Read required settings
        from ..settings import spotify_client_id
        client_id = spotify_client_id()
        redirect_uri = str(request.url_for("spotify_oauth_callback_get"))

        # Fail fast if configuration is missing
        if not client_id or not redirect_uri:
            from .metrics import SPOTIFY_OAUTH_ERRORS_TOTAL
            SPOTIFY_OAUTH_ERRORS_TOTAL.labels(error_type="missing_client_config").inc()
            logger.warning("Spotify OAuth misconfigured", extra={
                "client_id_present": bool(client_id),
                "redirect_uri_present": bool(redirect_uri),
                "req_id": req_id
            })
            raise HTTPException(status_code=503, detail="Spotify OAuth not configured")

        # Generate signed state for CSRF protection
        state = generate_signed_state()

        # Generate PKCE parameters for enhanced security
        code_verifier = generate_pkce_verifier()
        code_challenge = generate_pkce_challenge(code_verifier)

        # Build Spotify OAuth URL with proper scopes
        scopes = get_spotify_scopes()
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        # Handle next parameter
        next_url = request.query_params.get("next")
        if next_url:
            # Basic validation - only allow relative URLs or known safe domains
            if next_url.startswith("/") or next_url.startswith("http://localhost") or next_url.startswith("http://127.0.0.1"):
                params["state"] = f"{state}:{next_url}"

        auth_url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"

        # Rate-limited DEBUG logging of redirect_uri (once per hour)
        current_hour = int(time.time()) // 3600
        if not hasattr(spotify_login_url, '_last_logged_hour') or spotify_login_url._last_logged_hour != current_hour:
            logger.debug("Spotify OAuth redirect_uri configuration", extra={
                "redirect_uri": redirect_uri,
                "client_id_prefix": client_id[:20] + "..." if client_id else None,
                "req_id": req_id
            })
            spotify_login_url._last_logged_hour = current_hour

        # Create response with URL and set cookies
        response = Response(content=auth_url, media_type="text/plain")

        # Set state cookie
        from ..cookie_config import get_cookie_config
        cookie_config = get_cookie_config(request)
        cookies.set_named_cookie(
            response,
            name="s_state",
            value=state,
            ttl=600,
            httponly=cookie_config["httponly"],
            secure=cookie_config["secure"],
            samesite=cookie_config["samesite"],
        )

        # Set PKCE cookie
        cookies.set_named_cookie(
            response,
            name="s_pkce",
            value=code_verifier,
            ttl=600,
            httponly=cookie_config["httponly"],
            secure=cookie_config["secure"],
            samesite=cookie_config["samesite"],
        )

        # Set next cookie if provided
        if next_url:
            cookies.set_named_cookie(
                response,
                name="s_next",
                value=next_url,
                ttl=600,
                httponly=False,
                secure=True,
                samesite="lax",
            )

        return response

    except Exception as e:
        logger.error("spotify_login_url.failed", exc_info=True, extra={"error": str(e), "error_type": type(e).__name__})
        raise HTTPException(status_code=500, detail=f"Failed to generate login URL: {str(e)}")


@router.get("/callback", name="spotify_oauth_callback_get")
async def spotify_callback_get(request: Request) -> Response:
    """Handle Spotify OAuth callback via GET."""
    return await _spotify_callback_handler(request)


@router.post("/callback", name="spotify_oauth_callback_post")
async def spotify_callback_post(request: Request) -> Response:
    """Handle Spotify OAuth callback via POST."""
    return await _spotify_callback_handler(request)


@router.get("/status", name="spotify_oauth_status")
async def spotify_status(request: Request) -> Response:
    """Get Spotify OAuth status."""
    try:
        # Get current user from session/auth
        from ..auth.middleware import get_current_user_id
        try:
            user_id = get_current_user_id(request)
        except Exception:
            return Response(content='{"connected": false, "reason": "not_authenticated"}', media_type="application/json")
        
        # Check if user has valid Spotify tokens
        from ..auth_store_tokens import get_token
        token = await get_token(user_id, "spotify")
        
        if token and token.is_valid:
            return Response(content='{"connected": true, "user_id": "' + str(token.provider_user_id) + '"}', media_type="application/json")
        else:
            return Response(content='{"connected": false, "reason": "no_valid_token"}', media_type="application/json")
            
    except Exception as e:
        logger.error("Error checking Spotify OAuth status", exc_info=True, extra={"error": str(e)})
        return Response(content='{"connected": false, "reason": "error"}', media_type="application/json", status_code=500)


@router.post("/disconnect", name="spotify_oauth_disconnect")
async def spotify_disconnect(request: Request) -> Response:
    """Disconnect Spotify OAuth."""
    try:
        # Get current user from session/auth
        from ..auth.middleware import get_current_user_id
        try:
            user_id = get_current_user_id(request)
        except Exception:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Remove Spotify tokens
        from ..auth_store_tokens import mark_invalid
        await mark_invalid(user_id, "spotify")
        
        logger.info("Spotify OAuth disconnected", extra={"user_id": user_id})
        return Response(content='{"disconnected": true}', media_type="application/json")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error disconnecting Spotify OAuth", exc_info=True, extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Disconnect failed: {str(e)}")


@router.post("/refresh", name="spotify_oauth_refresh")
async def spotify_refresh(request: Request) -> Response:
    """Refresh Spotify OAuth token."""
    try:
        # Get current user from session/auth
        from ..auth.middleware import get_current_user_id
        try:
            user_id = get_current_user_id(request)
        except Exception:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Get and refresh token
        from ..integrations.spotify.refresh import SpotifyRefreshHelper
        refresh_helper = SpotifyRefreshHelper()
        
        success = await refresh_helper.refresh_spotify_token(user_id)
        
        if success:
            logger.info("Spotify token refreshed", extra={"user_id": user_id})
            return Response(content='{"refreshed": true}', media_type="application/json")
        else:
            logger.warning("Failed to refresh Spotify token", extra={"user_id": user_id})
            return Response(content='{"refreshed": false, "reason": "refresh_failed"}', media_type="application/json", status_code=400)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error refreshing Spotify OAuth token", exc_info=True, extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Refresh failed: {str(e)}")


async def _spotify_callback_handler(request: Request) -> Response:
    """Unified Spotify OAuth callback handler."""
    req_id = req_id_var.get()
    
    try:
        # Extract parameters from the callback
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")
        
        logger.info("Spotify OAuth callback received", extra={
            "has_code": bool(code),
            "has_state": bool(state),
            "has_error": bool(error),
            "req_id": req_id
        })
        
        # Handle OAuth errors
        if error:
            logger.error("Spotify OAuth error", extra={
                "error": error,
                "error_description": request.query_params.get("error_description"),
                "req_id": req_id
            })
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=f"{request.base_url}?error=oauth_error&details={error}")
        
        # Validate required parameters
        if not code or not state:
            logger.error("Missing required OAuth parameters", extra={
                "missing_code": not code,
                "missing_state": not state,
                "req_id": req_id
            })
            raise HTTPException(status_code=400, detail="Missing required OAuth parameters")
        
        # Validate state (CSRF protection)
        state_cookie = request.cookies.get("s_state")
        if not state_cookie:
            logger.error("Missing state cookie", extra={"req_id": req_id})
            raise HTTPException(status_code=400, detail="Missing state cookie")

        # Verify the signed state token
        from ..integrations.spotify.state import verify_signed_state
        if not verify_signed_state(state):
            logger.error("State validation failed", extra={
                "state_cookie_present": bool(state_cookie),
                "state_matches": state_cookie == state,
                "req_id": req_id
            })
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        # Get PKCE verifier from cookie
        code_verifier = request.cookies.get("s_pkce")
        if not code_verifier:
            logger.error("Missing PKCE verifier", extra={"req_id": req_id})
            raise HTTPException(status_code=400, detail="Missing PKCE verifier")
        
        # Exchange authorization code for tokens
        from ..integrations.spotify.oauth import exchange_code
        
        token_data = await exchange_code(code, code_verifier)
        
        if not token_data:
            logger.error("Token exchange failed", extra={"req_id": req_id})
            raise HTTPException(status_code=500, detail="Token exchange failed")
        
        # Get current user from session/auth
        from ..auth.middleware import get_current_user_id
        try:
            user_id = get_current_user_id(request)
        except Exception:
            logger.error("No authenticated user for OAuth callback", extra={"req_id": req_id})
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Store the OAuth token using the exchange_code function which handles token storage
        from ..auth_store_tokens import upsert_token
        from ..models.third_party_tokens import ThirdPartyToken
        from ..integrations.spotify.client import SpotifyClient
        
        # Get user profile to link identity
        temp_client = SpotifyClient(user_id="temp", access_token=token_data["access_token"])
        profile = await temp_client.get_user_profile()
        
        if not profile:
            logger.error("Failed to get user profile", extra={"req_id": req_id})
            raise HTTPException(status_code=500, detail="Failed to get user profile")
        
        # Create and store the token
        token = ThirdPartyToken(
            user_id=user_id,
            provider="spotify",
            provider_sub=profile["id"],
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_at=token_data.get("expires_at"),
            scopes=token_data.get("scope", "").split() if token_data.get("scope") else [],
            is_valid=True
        )
        
        await upsert_token(token)
        
        logger.info("Spotify OAuth completed successfully", extra={
            "user_id": user_id,
            "spotify_user_id": profile["id"],
            "req_id": req_id
        })
        
        # Redirect to success page or next URL
        next_url = request.cookies.get("s_next", "/")
        
        # Clear OAuth cookies
        from fastapi.responses import RedirectResponse
        response = RedirectResponse(url=next_url)
        response.delete_cookie("s_state")
        response.delete_cookie("s_pkce")
        response.delete_cookie("s_next")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Spotify OAuth callback error", exc_info=True, extra={
            "error": str(e),
            "error_type": type(e).__name__,
            "req_id": req_id
        })
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")
