"""
Unified redirect utilities for safe, single-decode redirects.

This module provides canonical redirect safety utilities that enforce:
- Single-decode enforcement (decode at most twice)
- Prevention of auth page redirects
- Same-origin relative paths only
- Strip fragments (#...), collapse //, remove nested ?next=...
- gs_next cookie support for post-login targets

Used by both frontend and backend for consistent redirect handling.

Cookie Security Rationale:
- SameSite=Lax: Allows cookies on top-level navigation while preventing CSRF
  from cross-site requests. More permissive than Strict but secure against
  common CSRF attacks.
- Short max-age (5 minutes default): gs_next cookies expire quickly to limit
  the window for replay attacks. Post-login redirects should happen immediately
  after authentication, so short TTL is appropriate.
- HttpOnly=True: Prevents JavaScript access to redirect cookies
- Secure: Set automatically based on request context (dev HTTP = false, production HTTPS = true)
"""

import logging
import os
from urllib.parse import urljoin, urlparse

from fastapi import Request, Response

logger = logging.getLogger(__name__)

# Import metrics for observability
try:
    from .metrics import AUTH_REDIRECT_SANITIZED_TOTAL
except ImportError:
    # Fallback for when metrics are not available
    class _StubCounter:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    AUTH_REDIRECT_SANITIZED_TOTAL = _StubCounter()

# Auth paths that should never be redirected to
AUTH_PATHS = {
    "/login",
    "/v1/auth/login",
    "/v1/auth/logout",
    "/v1/auth/refresh",
    "/v1/auth/csrf",
    "/google",
    "/oauth",
    "/sign-in",
    "/sign-up",
}

# Default fallback path
DEFAULT_FALLBACK = "/dashboard"


def is_auth_path(path: str) -> bool:
    """
    Check if path is an auth-related path that should not be redirected to.

    Auth paths are blocklisted to prevent redirect loops after authentication.
    Without this check, users could be redirected to login pages after successful
    login, creating an infinite cycle: login → redirect to login → login...
    This ensures post-authentication redirects always go to application content.
    """
    if not path:
        return False

    # Check exact matches first
    if path in AUTH_PATHS:
        return True

    # Check if path contains auth patterns
    for auth_path in AUTH_PATHS:
        if auth_path in path:
            return True

    return False


def safe_decode_url(url: str, max_decodes: int = 2) -> str:
    """
    Safely decode a URL-encoded string at most max_decodes times.

    Double-decoding is bounded to prevent infinite loops from malicious input
    that could contain nested encoding layers (e.g., %2520 = %20 encoded again).
    We limit to 2 decodes as sufficient for legitimate use while preventing DoS
    from attackers creating deeply nested encodings.

    Args:
        url: URL string to decode
        max_decodes: Maximum number of decode operations (default: 2)

    Returns:
        Decoded URL string
    """
    from urllib.parse import unquote

    decoded = url
    previous = url

    for _ in range(max_decodes):
        try:
            previous = decoded
            decoded = unquote(decoded)

            # Stop if no change (no more encoding layers)
            if decoded == previous:
                break
        except Exception:
            # If decoding fails at any point, use the last successfully decoded version
            decoded = previous
            break

    return decoded


def sanitize_redirect_path(
    raw_path: str | None,
    fallback: str = DEFAULT_FALLBACK,
    request: Request | None = None,
) -> str:
    """
    Sanitize a redirect path to prevent open redirects and nesting loops.

    Rules enforced:
    - Treat next as optional; fallback to DEFAULT_FALLBACK (or / if missing)
    - Never redirect to auth pages (/login, /v1/auth/*, /google/*, /oauth/*)
    - Only allow relative same-origin paths beginning with /
    - Decode at most twice; then stop
    - Strip fragments (#...), collapse //, remove any nested ?next=...
    - Normalize redundant slashes

    Args:
        raw_path: Raw path from user input (query param, form, etc.)
        fallback: Fallback path if input is invalid
        request: FastAPI Request object for origin validation

    Returns:
        Sanitized path that starts with / and is safe for redirects
    """
    if not raw_path or not isinstance(raw_path, str):
        AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="fallback_default").inc()
        logger.info(
            "Redirect sanitization fallback",
            extra={
                "component": "auth.redirect",
                "reason": "fallback_default",
                "input_len": 0,
                "output_path": fallback,
                "cookie_present": (
                    get_gs_next_cookie(request) is not None if request else False
                ),
                "env": os.getenv("ENV", "dev"),
                "raw_path": raw_path,
            },
        )
        return fallback

    path = raw_path.strip()
    if not path:
        AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="fallback_default").inc()
        logger.info(
            "Redirect sanitization fallback",
            extra={
                "component": "auth.redirect",
                "reason": "fallback_default",
                "input_len": len(raw_path) if raw_path else 0,
                "output_path": fallback,
                "cookie_present": (
                    get_gs_next_cookie(request) is not None if request else False
                ),
                "env": os.getenv("ENV", "dev"),
                "raw_path": raw_path,
            },
        )
        return fallback

    try:
        original_path = path
        sanitized = False

        # Step 1: Safe URL decoding (at most twice)
        decoded_path = safe_decode_url(path, max_decodes=2)
        if decoded_path != path:
            AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="double_decode").inc()
            logger.info(
                "Redirect sanitization",
                extra={
                    "component": "auth.redirect",
                    "reason": "double_decode",
                    "input_len": len(raw_path),
                    "output_path": fallback,
                    "cookie_present": (
                        get_gs_next_cookie(request) is not None if request else False
                    ),
                    "env": os.getenv("ENV", "dev"),
                    "raw_path": raw_path,
                    "decoded_path": decoded_path,
                },
            )
            return fallback
        path = decoded_path

        # Step 2: Reject absolute URLs to prevent open redirects
        if path.startswith(("http://", "https://")):
            AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="absolute_url").inc()
            logger.info(
                "Redirect sanitization",
                extra={
                    "component": "auth.redirect",
                    "reason": "absolute_url",
                    "input_len": len(raw_path),
                    "output_path": fallback,
                    "cookie_present": (
                        get_gs_next_cookie(request) is not None if request else False
                    ),
                    "env": os.getenv("ENV", "dev"),
                    "raw_path": raw_path,
                },
            )
            return fallback

        # Step 3: Reject protocol-relative URLs
        if path.startswith("//") and not path.startswith("///"):
            AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="protocol_relative").inc()
            logger.info(
                "Redirect sanitization",
                extra={
                    "component": "auth.redirect",
                    "reason": "protocol_relative",
                    "input_len": len(raw_path),
                    "output_path": fallback,
                    "cookie_present": (
                        get_gs_next_cookie(request) is not None if request else False
                    ),
                    "env": os.getenv("ENV", "dev"),
                    "raw_path": raw_path,
                },
            )
            return fallback

        # Step 4: Ensure path starts with /
        if not path.startswith("/"):
            AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="fallback_default").inc()
            logger.info(
                "Redirect sanitization fallback",
                extra={
                    "component": "auth.redirect",
                    "reason": "fallback_default",
                    "input_len": len(raw_path),
                    "output_path": fallback,
                    "cookie_present": (
                        get_gs_next_cookie(request) is not None if request else False
                    ),
                    "env": os.getenv("ENV", "dev"),
                    "raw_path": raw_path,
                },
            )
            return fallback

        # Step 5: Strip fragments (#...)
        if "#" in path:
            path = path.split("#")[0]
            sanitized = True

        # Step 6: Remove any nested ?next=... parameters
        if "?" in path:
            from urllib.parse import parse_qs, urlencode, urlparse

            parsed = urlparse(path)
            query_params = parse_qs(parsed.query)

            # Remove any next parameters
            if "next" in query_params:
                del query_params["next"]
                sanitized = True
                AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="removed_nested_next").inc()
                logger.info(
                    "Redirect sanitization",
                    extra={
                        "component": "auth.redirect",
                        "reason": "removed_nested_next",
                        "input_len": len(raw_path),
                        "output_path": path if query_params else parsed.path,
                        "cookie_present": (
                            get_gs_next_cookie(request) is not None
                            if request
                            else False
                        ),
                        "env": os.getenv("ENV", "dev"),
                        "raw_path": raw_path,
                    },
                )

            # Reconstruct path without next params
            if query_params:
                new_query = urlencode(query_params, doseq=True)
                path = f"{parsed.path}?{new_query}"
            else:
                path = parsed.path

        # Step 7: Prevent redirect loops by blocking auth-related paths
        if is_auth_path(path):
            AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="blocked_auth_path").inc()
            logger.info(
                "Redirect sanitization",
                extra={
                    "component": "auth.redirect",
                    "reason": "blocked_auth_path",
                    "input_len": len(raw_path),
                    "output_path": fallback,
                    "cookie_present": (
                        get_gs_next_cookie(request) is not None if request else False
                    ),
                    "env": os.getenv("ENV", "dev"),
                    "raw_path": raw_path,
                },
            )
            return fallback

        # Step 8: Normalize redundant slashes
        import re

        normalized_path = re.sub(r"/+", "/", path)
        if normalized_path != path:
            AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="normalized_slashes").inc()
            logger.info(
                "Redirect sanitization",
                extra={
                    "component": "auth.redirect",
                    "reason": "normalized_slashes",
                    "input_len": len(raw_path),
                    "output_path": normalized_path,
                    "cookie_present": (
                        get_gs_next_cookie(request) is not None if request else False
                    ),
                    "env": os.getenv("ENV", "dev"),
                    "raw_path": raw_path,
                    "original_path": original_path,
                    "normalized_path": normalized_path,
                },
            )
            return normalized_path

        # Step 9: Basic path validation (no .. traversal)
        if ".." in path:
            AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="fallback_default").inc()
            logger.info(
                "Redirect sanitization fallback",
                extra={
                    "component": "auth.redirect",
                    "reason": "fallback_default",
                    "input_len": len(raw_path),
                    "output_path": fallback,
                    "cookie_present": (
                        get_gs_next_cookie(request) is not None if request else False
                    ),
                    "env": os.getenv("ENV", "dev"),
                    "raw_path": raw_path,
                },
            )
            return fallback

        # Success case - log if any sanitization occurred
        if sanitized:
            logger.info(
                "Redirect sanitization success",
                extra={
                    "component": "auth.redirect",
                    "reason": "success",
                    "input_len": len(raw_path),
                    "output_path": path,
                    "cookie_present": (
                        get_gs_next_cookie(request) is not None if request else False
                    ),
                    "env": os.getenv("ENV", "dev"),
                    "raw_path": raw_path,
                    "sanitized_path": path,
                },
            )

        return path

    except Exception as e:
        AUTH_REDIRECT_SANITIZED_TOTAL.labels(reason="fallback_default").inc()
        logger.error(
            "Error sanitizing redirect path %s: %s",
            raw_path,
            e,
            extra={
                "component": "auth.redirect",
                "reason": "fallback_default",
                "input_len": len(raw_path) if raw_path else 0,
                "output_path": fallback,
                "cookie_present": (
                    get_gs_next_cookie(request) is not None if request else False
                ),
                "env": os.getenv("ENV", "dev"),
                "raw_path": raw_path,
                "error": str(e),
            },
        )
        return fallback


def get_safe_redirect_target(
    request: Request, next_param: str | None = None, fallback: str = DEFAULT_FALLBACK
) -> str:
    """
    Get a safe redirect target from request parameters and cookies.

    Priority order:
    1. Explicit next parameter (if provided)
    2. gs_next cookie (post-login target)
    3. Fallback path

    Args:
        request: FastAPI Request object
        next_param: Explicit next parameter (e.g., from query string)
        fallback: Default fallback path

    Returns:
        Safe redirect path
    """
    # Priority 1: Explicit next parameter
    if next_param:
        sanitized = sanitize_redirect_path(next_param, fallback, request)
        if sanitized != fallback:  # Only use if it wasn't rejected
            return sanitized

    # Priority 2: gs_next cookie for post-login targets
    gs_next = get_gs_next_cookie(request)
    if gs_next:
        sanitized = sanitize_redirect_path(gs_next, fallback, request)
        if sanitized != fallback:  # Only use if it wasn't rejected
            # Clear the cookie after use
            clear_gs_next_cookie(None, request)  # Will be called by response later
            return sanitized

    # Priority 3: Fallback
    return fallback


def set_gs_next_cookie(
    response: Response,
    path: str,
    request: Request,
    ttl_seconds: int = 300,  # 5 minutes default
) -> None:
    """
    Set the gs_next cookie for post-login redirect target.

    Args:
        response: FastAPI Response object
        path: Safe redirect path to store
        request: FastAPI Request object for cookie config
        ttl_seconds: Cookie TTL in seconds (default: 5 minutes)
    """
    if not path or not path.startswith("/"):
        logger.warning("Invalid gs_next path: %s", path)
        return

    try:
        from .cookie_config import format_cookie_header, get_cookie_config

        # Use centralized cookie configuration
        cfg = get_cookie_config(request)
        same_site = str(cfg.get("samesite", "lax")).capitalize()
        secure = bool(cfg.get("secure", True))

        cookie_value = format_cookie_header(
            "gs_next",
            path,
            max_age=ttl_seconds,
            secure=secure,
            samesite=same_site,
            path="/",
            httponly=True,
        )

        response.headers.append("set-cookie", cookie_value)
        logger.debug("Set gs_next cookie: %s", path)

    except Exception as e:
        logger.error("Failed to set gs_next cookie: %s", e)


def get_gs_next_cookie(request: Request) -> str | None:
    """
    Get the gs_next cookie value.

    Args:
        request: FastAPI Request object

    Returns:
        Cookie value or None if not present
    """
    try:
        return request.cookies.get("gs_next")
    except Exception:
        return None


def clear_gs_next_cookie(response: Response, request: Request) -> None:
    """
    Clear the gs_next cookie.

    Args:
        response: FastAPI Response object
        request: FastAPI Request object
    """
    try:
        from .cookie_config import format_cookie_header, get_cookie_config

        # Use centralized cookie configuration
        cfg = get_cookie_config(request)
        same_site = str(cfg.get("samesite", "lax")).capitalize()
        secure = bool(cfg.get("secure", True))

        cookie_value = format_cookie_header(
            "gs_next",
            "",  # Empty value
            max_age=0,  # Expire immediately
            secure=secure,
            samesite=same_site,
            path="/",
            httponly=True,
        )

        response.headers.append("set-cookie", cookie_value)
        logger.debug("Cleared gs_next cookie")

    except Exception as e:
        logger.error("Failed to clear gs_next cookie: %s", e)


def build_origin_aware_redirect_url(request: Request, path: str) -> str:
    """
    Build an origin-aware redirect URL from the request.

    Args:
        request: FastAPI Request object
        path: Relative path to redirect to (must start with /)

    Returns:
        Full URL for redirect

    Raises:
        ValueError: If path doesn't start with /
    """
    if not path.startswith("/"):
        raise ValueError("Path must start with / for security")
    if not path.startswith("/"):
        raise ValueError("Path must start with / for security")

    try:
        # Get origin from request headers
        origin = request.headers.get("origin") or request.headers.get("referer")

        if origin:
            try:
                parsed = urlparse(origin)
                if parsed.scheme and parsed.netloc:
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    return urljoin(base_url, path)
            except Exception:
                pass

        # Fallback: derive from request URL
        try:
            url_str = str(request.url)
            if url_str.startswith(("http://", "https://")):
                parsed = urlparse(url_str)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                return urljoin(base_url, path)
        except Exception:
            pass

        # Last resort: use environment variables
        logger.warning(
            "Using fallback APP_URL for redirect - consider fixing request origin"
        )
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        return urljoin(app_url, path)

    except Exception as e:
        logger.error("Error building origin-aware redirect URL: %s", e)
        # Ultimate fallback
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        return urljoin(app_url, path)
