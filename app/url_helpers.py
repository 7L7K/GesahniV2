"""
Centralized URL utilities for building URLs consistently across the backend.
Avoids hardcoding URLs and ensures consistent URL derivation.
"""

import os
from typing import Optional
from urllib.parse import urljoin, urlparse
from fastapi import Request


def get_app_url() -> str:
    """
    Get the base URL for the application.
    
    Returns:
        str: Base URL (e.g., 'http://localhost:8000')
    """
    # Check for explicit APP_URL configuration
    app_url = os.getenv("APP_URL")
    if app_url:
        return app_url.rstrip('/')
    
    # Derive from host and port
    host = os.getenv("HOST", "localhost")
    port = os.getenv("PORT", "8000")
    scheme = "https" if os.getenv("FORCE_HTTPS", "0").lower() in {"1", "true", "yes", "on"} else "http"
    
    # Ensure we always return a valid URL, never None or undefined
    result = f"{scheme}://{host}:{port}"
    
    # Log when we have to fall back to derived URL so we can spot it early
    if not app_url:
        import logging
        logging.warning(f"APP_URL not configured, using derived URL: {result}. Consider setting APP_URL explicitly.")
    
    return result


def get_frontend_url() -> str:
    """
    Get the frontend URL from CORS configuration.
    
    Returns:
        str: Frontend URL (e.g., 'http://localhost:3000')
    """
    cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
    # Use first origin if multiple are configured
    if "," in cors_origins:
        cors_origins = cors_origins.split(",")[0]
    return cors_origins.strip()


def build_ws_url(path: str, base_url: Optional[str] = None) -> str:
    """
    Build a WebSocket URL from the base URL.
    
    Args:
        path: WebSocket path (e.g., '/v1/ws/care')
        base_url: Optional base URL, defaults to APP_URL
        
    Returns:
        str: WebSocket URL
    """
    if base_url is None:
        base_url = get_app_url()
    
    # Convert HTTP to WebSocket scheme
    parsed = urlparse(base_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_base = f"{ws_scheme}://{parsed.netloc}"
    
    return urljoin(ws_base, path)


def build_api_url(path: str, base_url: Optional[str] = None) -> str:
    """
    Build an API URL from the base URL.
    
    Args:
        path: API path (e.g., '/v1/auth/login')
        base_url: Optional base URL, defaults to APP_URL
        
    Returns:
        str: API URL
    """
    if base_url is None:
        base_url = get_app_url()
    
    return urljoin(base_url, path)


def is_dev_environment() -> bool:
    """
    Check if we're in a development environment.
    
    Returns:
        bool: True if in development environment
    """
    dev_indicators = [
        os.getenv("PYTEST_CURRENT_TEST"),  # Running tests
        os.getenv("FLASK_ENV") == "development",
        os.getenv("ENVIRONMENT") == "development",
        os.getenv("NODE_ENV") == "development",
    ]
    
    return any(dev_indicators)


def build_origin_aware_url(request: Request, path: str) -> str:
    """Build a URL relative to the request's origin to avoid hardcoded hosts in redirects.
    
    This function ensures that all redirects are origin-aware and don't use hardcoded
    localhost URLs, which is critical for proper deployment across different environments.
    
    Args:
        request: FastAPI Request object
        path: Relative path to redirect to (must start with /)
        
    Returns:
        Full URL for redirect
        
    Raises:
        ValueError: If path doesn't start with /
    """
    if not path.startswith('/'):
        raise ValueError("Path must start with / for security")
    
    # Get the origin from the request headers
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            return f"{base_url}{path}"
        except Exception:
            pass
    
    # Fallback: use the request URL to derive the base
    try:
        from urllib.parse import urlparse
        url_str = str(request.url)
        if not url_str.startswith(('http://', 'https://')):
            raise ValueError("Invalid URL scheme")
        parsed = urlparse(url_str)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        return f"{base_url}{path}"
    except Exception:
        # Last resort: use environment variable but log warning
        import logging
        logging.warning("Using fallback APP_URL for redirect - consider fixing request origin")
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        return f"{app_url}{path}"

def sanitize_redirect_path(path: str, fallback: str = "/") -> str:
    """Sanitize a redirect path to prevent open redirects.
    
    Args:
        path: Raw path from user input
        fallback: Fallback path if input is invalid
        
    Returns:
        Sanitized path that starts with / and doesn't contain protocol
    """
    if not path or not isinstance(path, str):
        return fallback
    
    path = path.strip()
    
    # Reject absolute URLs to prevent open redirects
    if path.startswith(('http://', 'https://')):
        return fallback
    # Reject protocol-relative URLs (starting with // but not ///)
    if path.startswith('//') and not path.startswith('///'):
        return fallback
    
    # Ensure path starts with /
    if not path.startswith('/'):
        return fallback
    
    # Normalize multiple slashes but preserve trailing slash
    import re
    has_trailing = path.endswith('/')
    path = re.sub(r'/+', '/', path)
    
    # If the path is just "/" and originally had trailing slash, keep it
    if path == "/" and has_trailing:
        return "/"
    # If the path is just "/" and originally didn't have trailing slash, keep it
    elif path == "/" and not has_trailing:
        return "/"
    # If we had trailing slash but lost it, add it back
    elif has_trailing and not path.endswith('/'):
        path += '/'
    
    return path
