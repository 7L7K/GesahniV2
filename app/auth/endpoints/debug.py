"""Auth debug and info endpoints for frontend diagnostics."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request

from ...cookie_config import get_cookie_config, get_token_ttls
from ...deps.user import get_current_user_id
from ...auth_refresh import _jwt_secret

router = APIRouter(tags=["Auth"])


@router.get("/auth/cookie-config")
async def debug_cookie_config(request: Request) -> dict[str, Any]:
    """Return cookie configuration for frontend debugging."""
    try:
        config = get_cookie_config(request)
        access_ttl, refresh_ttl = get_token_ttls()
        
        return {
            "cookie_domain": config.get("domain"),
            "cookie_path": config.get("path", "/"),
            "cookie_samesite": config.get("samesite", "Lax"),
            "cookie_secure": config.get("secure", False),
            "access_ttl": access_ttl,
            "refresh_ttl": refresh_ttl,
            "csrf_enabled": os.getenv("CSRF_ENABLED", "0") == "1",
            "auth_cookies_enabled": os.getenv("AUTH_COOKIES_ENABLED", "0") == "1",
        }
    except Exception as e:
        return {"error": str(e), "cookie_config": "unavailable"}


@router.get("/auth/session-info")
async def debug_session_info(request: Request) -> dict[str, Any]:
    """Return session information for frontend debugging."""
    try:
        # Get current user info
        user_id = await get_current_user_id(request=request)
        
        # Extract session info from cookies/headers
        cookies = request.cookies
        headers = dict(request.headers)
        
        # Check for auth cookies
        auth_cookies = {
            "GSNH_AT": cookies.get("GSNH_AT") is not None,
            "GSNH_RT": cookies.get("GSNH_RT") is not None,
            "GSNH_SESS": cookies.get("GSNH_SESS") is not None,
            "device_id": cookies.get("device_id") is not None,
        }
        
        return {
            "user_id": user_id,
            "is_authenticated": user_id != "anon",
            "session_ready": user_id != "anon",
            "auth_cookies": auth_cookies,
            "has_auth_header": "Authorization" in headers,
            "csrf_token_present": cookies.get("csrf_token") is not None,
        }
    except Exception as e:
        return {"error": str(e), "session_info": "unavailable"}


@router.get("/auth/jwt-info")
async def debug_jwt_info(request: Request) -> dict[str, Any]:
    """Return JWT token information for frontend debugging."""
    try:
        import jwt
        from ...cookies import read_access_cookie, read_refresh_cookie
        
        result = {
            "jwt_secret_configured": bool(_jwt_secret()),
            "access_token": None,
            "refresh_token": None,
            "tokens_valid": False,
        }
        
        # Check access token
        access_token = read_access_cookie(request)
        if access_token:
            try:
                payload = jwt.decode(access_token, _jwt_secret(), algorithms=["HS256"])
                result["access_token"] = {
                    "present": True,
                    "user_id": payload.get("user_id"),
                    "exp": payload.get("exp"),
                    "type": payload.get("type"),
                    "valid": True,
                }
                result["tokens_valid"] = True
            except Exception as e:
                result["access_token"] = {
                    "present": True,
                    "valid": False,
                    "error": str(e),
                }
        else:
            result["access_token"] = {"present": False}
            
        # Check refresh token
        refresh_token = read_refresh_cookie(request)
        if refresh_token:
            try:
                payload = jwt.decode(refresh_token, _jwt_secret(), algorithms=["HS256"])
                result["refresh_token"] = {
                    "present": True,
                    "user_id": payload.get("user_id"),
                    "exp": payload.get("exp"),
                    "type": payload.get("type"),
                    "valid": True,
                }
            except Exception as e:
                result["refresh_token"] = {
                    "present": True,
                    "valid": False,
                    "error": str(e),
                }
        else:
            result["refresh_token"] = {"present": False}
            
        return result
    except Exception as e:
        return {"error": str(e), "jwt_info": "unavailable"}


@router.get("/auth/refresh-info")
async def debug_refresh_info(request: Request) -> dict[str, Any]:
    """Return refresh token status for frontend debugging."""
    try:
        from ...cookies import read_refresh_cookie
        from ...token_store import is_refresh_valid
        
        refresh_token = read_refresh_cookie(request)
        
        result = {
            "refresh_token_present": refresh_token is not None,
            "refresh_valid": False,
            "refresh_info": None,
        }
        
        if refresh_token:
            try:
                # Check if refresh token is valid in store (simplified check)
                # For now, just check if token is decodable and not expired
                import jwt
                import time
                try:
                    payload = jwt.decode(refresh_token, _jwt_secret(), algorithms=["HS256"])
                    exp = payload.get("exp", 0)
                    is_valid = exp > time.time()
                    result["refresh_valid"] = is_valid
                except Exception:
                    result["refresh_valid"] = False
                
                # Decode token for info (without verification since we just want info)
                import jwt
                payload = jwt.decode(refresh_token, options={"verify_signature": False})
                result["refresh_info"] = {
                    "user_id": payload.get("user_id"),
                    "jti": payload.get("jti"),
                    "exp": payload.get("exp"),
                    "iat": payload.get("iat"),
                }
            except Exception as e:
                result["refresh_info"] = {"error": str(e)}
                
        return result
    except Exception as e:
        return {"error": str(e), "refresh_info": "unavailable"}


@router.get("/auth/env-info")
async def debug_env_info() -> dict[str, Any]:
    """Return auth-related environment configuration."""
    return {
        "environment": os.getenv("ENV", "dev"),
        "auth_cookies_enabled": os.getenv("AUTH_COOKIES_ENABLED", "0") == "1",
        "csrf_enabled": os.getenv("CSRF_ENABLED", "0") == "1",
        "jwt_secret_configured": bool(os.getenv("JWT_SECRET")),
        "database_url_configured": bool(os.getenv("DATABASE_URL")),
        "cors_origins": os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if os.getenv("CORS_ALLOW_ORIGINS") else [],
        "cookie_domain": os.getenv("COOKIE_DOMAIN"),
        "cookie_secure": os.getenv("COOKIE_SECURE", "auto"),
        "cookie_samesite": os.getenv("COOKIE_SAMESITE", "Lax"),
    }


async def debug_auth_state(request: Request) -> dict[str, Any]:
    """Debug authentication state for frontend."""
    try:
        user_id = await get_current_user_id(request=request)
        session_info = await debug_session_info(request)
        jwt_info = await debug_jwt_info(request)
        
        return {
            "user_id": user_id,
            "is_authenticated": user_id != "anon",
            "session_info": session_info,
            "jwt_info": jwt_info,
        }
    except Exception as e:
        return {"error": str(e), "auth_state": "unavailable"}


async def debug_cookies(request: Request) -> dict[str, Any]:
    """Debug cookie information - used by alias router."""
    cookies = dict(request.cookies)
    
    # Sanitize sensitive cookie values for logging
    sanitized = {}
    for key, value in cookies.items():
        if key.startswith("GSNH_") or "token" in key.lower():
            sanitized[key] = f"<{len(value)} chars>" if value else None
        else:
            sanitized[key] = value
            
    return {
        "cookies": sanitized,
        "cookie_count": len(cookies),
        "auth_cookies": {
            "access_token": "GSNH_AT" in cookies,
            "refresh_token": "GSNH_RT" in cookies,
            "session_id": "GSNH_SESS" in cookies,
            "device_id": "device_id" in cookies,
            "csrf_token": "csrf_token" in cookies,
        }
    }


@router.get("/auth/whoami")
async def auth_whoami_endpoint(request: Request) -> dict[str, Any]:
    """Main whoami endpoint for authentication checking."""
    try:
        from ...api.auth import whoami_impl
        return await whoami_impl(request)
    except Exception as e:
        return {"error": str(e), "whoami": "unavailable"}


async def whoami(request: Request) -> dict[str, Any]:
    """Debug whoami function for compatibility - non-routed version."""
    try:
        from ...api.auth import whoami_impl
        return await whoami_impl(request)
    except Exception as e:
        return {"error": str(e), "whoami": "unavailable"}