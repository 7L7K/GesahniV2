"""Authentication diagnostic endpoints for enhanced debugging and monitoring."""

import logging
import os
import time
from datetime import UTC, datetime
from typing import Any, Dict

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.auth.jwt_utils import _decode_any
from app.cookie_config import get_cookie_config
from app.cookies import read_access_cookie, read_refresh_cookie, read_session_cookie
from app.csrf import CSRFTokenService
from app.logging_config import req_id_var

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/auth", tags=["Auth Diagnostics"])


@router.get("/cookie-config")
async def get_cookie_config_info(request: Request) -> JSONResponse:
    """Get current cookie configuration for debugging."""
    try:
        config = get_cookie_config(request)
        return JSONResponse({
            "samesite": config.get("samesite", "lax"),
            "secure": config.get("secure", False),
            "domain": config.get("domain"),
            "path": config.get("path", "/"),
            "httponly": config.get("httponly", True),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        })
    except Exception as e:
        logger.error(f"cookie_config.error: {e}")
        return JSONResponse({
            "error": str(e),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        }, status_code=500)


@router.get("/jwt-info")
async def get_jwt_info(request: Request) -> JSONResponse:
    """Get JWT token information for debugging."""
    try:
        access_token = read_access_cookie(request)
        
        if not access_token:
            return JSONResponse({
                "token_present": False,
                "error": "No access token found",
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })

        try:
            claims = _decode_any(access_token)
            if not isinstance(claims, dict):
                raise ValueError("Invalid claims format")

            exp_time = claims.get("exp")
            iat_time = claims.get("iat")
            current_time = time.time()

            return JSONResponse({
                "token_present": True,
                "expires_at": datetime.fromtimestamp(exp_time, UTC).isoformat() if exp_time else None,
                "issued_at": datetime.fromtimestamp(iat_time, UTC).isoformat() if iat_time else None,
                "ttl_seconds": int(exp_time - current_time) if exp_time else None,
                "is_expired": exp_time < current_time if exp_time else None,
                "claims": {k: v for k, v in claims.items() if k not in ["exp", "iat", "nbf"]},
                "user_id": claims.get("user_id") or claims.get("sub"),
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })
        except Exception as e:
            return JSONResponse({
                "token_present": True,
                "token_valid": False,
                "error": str(e),
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })

    except Exception as e:
        logger.error(f"jwt_info.error: {e}")
        return JSONResponse({
            "error": str(e),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        }, status_code=500)


@router.get("/session-info")
async def get_session_info(request: Request) -> JSONResponse:
    """Get session information for debugging."""
    try:
        session_id = read_session_cookie(request)
        
        if not session_id:
            return JSONResponse({
                "session_present": False,
                "error": "No session cookie found",
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })

        # Try to get session from store
        session_data = None
        store_status = "unknown"
        try:
            from app.session_store import get_session_store
            store = get_session_store()
            session_data = store.get_session(session_id)
            store_status = "available" if session_data else "not_found"
        except Exception as e:
            store_status = f"error: {str(e)}"

        return JSONResponse({
            "session_present": True,
            "session_id": session_id,
            "store_status": store_status,
            "session_data": session_data,
            "created_at": session_data.get("created_at") if session_data else None,
            "last_activity": session_data.get("last_activity") if session_data else None,
            "expires_at": session_data.get("expires_at") if session_data else None,
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        })

    except Exception as e:
        logger.error(f"session_info.error: {e}")
        return JSONResponse({
            "error": str(e),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        }, status_code=500)


@router.get("/refresh-info")
async def get_refresh_info(request: Request) -> JSONResponse:
    """Get refresh token information for debugging."""
    try:
        refresh_token = read_refresh_cookie(request)
        
        if not refresh_token:
            return JSONResponse({
                "refresh_present": False,
                "error": "No refresh token found",
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })

        try:
            claims = _decode_any(refresh_token)
            if not isinstance(claims, dict):
                raise ValueError("Invalid claims format")

            exp_time = claims.get("exp")
            current_time = time.time()
            family_id = claims.get("family_id") or claims.get("jti")

            # Check if rotation is eligible (token expires within 5 minutes)
            rotation_eligible = exp_time and (exp_time - current_time) < 300

            return JSONResponse({
                "refresh_present": True,
                "available": True,
                "expires_at": datetime.fromtimestamp(exp_time, UTC).isoformat() if exp_time else None,
                "is_expired": exp_time < current_time if exp_time else None,
                "rotation_eligible": rotation_eligible,
                "family_id": family_id,
                "user_id": claims.get("user_id") or claims.get("sub"),
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })
        except Exception as e:
            return JSONResponse({
                "refresh_present": True,
                "available": False,
                "error": str(e),
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })

    except Exception as e:
        logger.error(f"refresh_info.error: {e}")
        return JSONResponse({
            "error": str(e),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        }, status_code=500)


@router.get("/env-info")
async def get_env_info(request: Request) -> JSONResponse:
    """Get environment and configuration information for debugging."""
    try:
        # Get environment variables (safe ones only)
        env_vars = {
            "ENV": os.getenv("ENV", "dev"),
            "DEV_MODE": os.getenv("DEV_MODE", "0"),
            "AUTH_DEBUG": os.getenv("AUTH_DEBUG", "0"),
            "COOKIE_SECURE": os.getenv("COOKIE_SECURE", "auto"),
            "COOKIE_SAMESITE": os.getenv("COOKIE_SAMESITE", "lax"),
            "CORS_ALLOW_ORIGINS": os.getenv("CORS_ALLOW_ORIGINS", ""),
            "JWT_EXPIRE_MINUTES": os.getenv("JWT_EXPIRE_MINUTES", "30"),
            "JWT_REFRESH_EXPIRE_MINUTES": os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"),
        }

        # Determine mode
        dev_mode = env_vars["DEV_MODE"].lower() in {"1", "true", "yes", "on"}
        mode = "development" if dev_mode else "production"

        # Get CORS origins
        cors_origins = env_vars["CORS_ALLOW_ORIGINS"].split(",") if env_vars["CORS_ALLOW_ORIGINS"] else []

        return JSONResponse({
            "mode": mode,
            "dev_mode": dev_mode,
            "auth_debug": env_vars["AUTH_DEBUG"].lower() in {"1", "true", "yes", "on"},
            "cors_origins": cors_origins,
            "cookie_secure": env_vars["COOKIE_SECURE"],
            "cookie_samesite": env_vars["COOKIE_SAMESITE"],
            "jwt_expire_minutes": int(env_vars["JWT_EXPIRE_MINUTES"]),
            "jwt_refresh_expire_minutes": int(env_vars["JWT_REFRESH_EXPIRE_MINUTES"]),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        })

    except Exception as e:
        logger.error(f"env_info.error: {e}")
        return JSONResponse({
            "error": str(e),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        }, status_code=500)


@router.get("/csrf-info")
async def get_csrf_info(request: Request) -> JSONResponse:
    """Get CSRF token information for debugging."""
    try:
        # Get CSRF token from cookie
        csrf_token = request.cookies.get("csrf_token")
        
        if not csrf_token:
            return JSONResponse({
                "token_present": False,
                "error": "No CSRF token found",
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })

        # Validate CSRF token
        try:
            csrf_service = CSRFTokenService()
            is_valid = csrf_service.validate_token(csrf_token)
            
            # Try to extract expiration info
            expires_at = None
            try:
                parts = csrf_token.split(".")
                if len(parts) >= 2:
                    timestamp = int(parts[1])
                    expires_at = datetime.fromtimestamp(timestamp + csrf_service.ttl_seconds, UTC).isoformat()
            except Exception:
                pass

            return JSONResponse({
                "token_present": True,
                "valid": is_valid,
                "expires_at": expires_at,
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })
        except Exception as e:
            return JSONResponse({
                "token_present": True,
                "valid": False,
                "error": str(e),
                "request_id": req_id_var.get(),
                "timestamp": datetime.now(UTC).isoformat()
            })

    except Exception as e:
        logger.error(f"csrf_info.error: {e}")
        return JSONResponse({
            "error": str(e),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        }, status_code=500)


@router.get("/comprehensive")
async def get_comprehensive_auth_info(request: Request) -> JSONResponse:
    """Get comprehensive authentication information in a single request."""
    try:
        start_time = time.time()
        
        # Gather all diagnostic information
        cookie_config = get_cookie_config(request)
        access_token = read_access_cookie(request)
        refresh_token = read_refresh_cookie(request)
        session_id = read_session_cookie(request)
        csrf_token = request.cookies.get("csrf_token")
        
        # JWT info
        jwt_info = {}
        if access_token:
            try:
                claims = _decode_any(access_token)
                if isinstance(claims, dict):
                    exp_time = claims.get("exp")
                    current_time = time.time()
                    jwt_info = {
                        "present": True,
                        "valid": True,
                        "expires_at": datetime.fromtimestamp(exp_time, UTC).isoformat() if exp_time else None,
                        "ttl_seconds": int(exp_time - current_time) if exp_time else None,
                        "is_expired": exp_time < current_time if exp_time else None,
                        "user_id": claims.get("user_id") or claims.get("sub")
                    }
                else:
                    jwt_info = {"present": True, "valid": False, "error": "Invalid claims format"}
            except Exception as e:
                jwt_info = {"present": True, "valid": False, "error": str(e)}
        else:
            jwt_info = {"present": False, "valid": False}
        
        # Refresh token info
        refresh_info = {}
        if refresh_token:
            try:
                claims = _decode_any(refresh_token)
                if isinstance(claims, dict):
                    exp_time = claims.get("exp")
                    current_time = time.time()
                    refresh_info = {
                        "present": True,
                        "valid": True,
                        "expires_at": datetime.fromtimestamp(exp_time, UTC).isoformat() if exp_time else None,
                        "rotation_eligible": exp_time and (exp_time - current_time) < 300,
                        "family_id": claims.get("family_id") or claims.get("jti")
                    }
                else:
                    refresh_info = {"present": True, "valid": False, "error": "Invalid claims format"}
            except Exception as e:
                refresh_info = {"present": True, "valid": False, "error": str(e)}
        else:
            refresh_info = {"present": False, "valid": False}
        
        # CSRF info
        csrf_info = {}
        if csrf_token:
            try:
                csrf_service = CSRFTokenService()
                is_valid = csrf_service.validate_token(csrf_token)
                csrf_info = {"present": True, "valid": is_valid}
            except Exception as e:
                csrf_info = {"present": True, "valid": False, "error": str(e)}
        else:
            csrf_info = {"present": False, "valid": False}
        
        # Session info
        session_info = {}
        if session_id:
            try:
                from app.session_store import get_session_store
                store = get_session_store()
                session_data = store.get_session(session_id)
                session_info = {
                    "present": True,
                    "store_available": session_data is not None,
                    "session_id": session_id,
                    "data": session_data
                }
            except Exception as e:
                session_info = {"present": True, "store_available": False, "error": str(e)}
        else:
            session_info = {"present": False, "store_available": False}
        
        processing_time = int((time.time() - start_time) * 1000)
        
        return JSONResponse({
            "cookie_config": {
                "samesite": cookie_config.get("samesite", "lax"),
                "secure": cookie_config.get("secure", False),
                "domain": cookie_config.get("domain"),
                "path": cookie_config.get("path", "/"),
                "httponly": cookie_config.get("httponly", True)
            },
            "jwt": jwt_info,
            "refresh": refresh_info,
            "csrf": csrf_info,
            "session": session_info,
            "cookies": {
                "access_present": bool(access_token),
                "refresh_present": bool(refresh_token),
                "session_present": bool(session_id),
                "csrf_present": bool(csrf_token),
                "total_count": len(request.cookies)
            },
            "processing_time_ms": processing_time,
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        })

    except Exception as e:
        logger.error(f"comprehensive_auth_info.error: {e}")
        return JSONResponse({
            "error": str(e),
            "request_id": req_id_var.get(),
            "timestamp": datetime.now(UTC).isoformat()
        }, status_code=500)

