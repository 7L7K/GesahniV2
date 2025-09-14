"""
Redirect sanitization module for secure redirect handling.

This module provides canonical redirect safety utilities that enforce:
- Single-decode enforcement (decode at most twice)
- Prevention of auth page redirects
- Same-origin relative paths only
- Strip fragments (#...), collapse //, remove nested ?next=...
- Blocklist enforcement for auth paths
"""

import logging
import re
from urllib.parse import parse_qs, unquote, urlencode, urlparse

logger = logging.getLogger(__name__)

# Default fallback path
DEFAULT_REDIRECT = "/dashboard"

# Auth paths that should never be redirected to (exact match or prefix match)
BLOCKLIST_PATHS = {"/login", "/v1/auth", "/google", "/oauth"}


def safe_decode_url(url: str, max_decodes: int = 2) -> str:
    """
    Safely decode a URL-encoded string at most max_decodes times.

    Args:
        url: URL string to decode
        max_decodes: Maximum number of decode operations (default: 2)

    Returns:
        Decoded URL string
    """
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


def is_blocklisted_path(path: str) -> bool:
    """
    Check if path is blocked for redirects.

    Uses exact match or prefix match for blocklisted paths.

    Args:
        path: Path to check

    Returns:
        True if path is blocklisted
    """
    if not path:
        return False

    # Check exact matches and prefix matches
    for blocked_path in BLOCKLIST_PATHS:
        if path == blocked_path or path.startswith(blocked_path + "/"):
            return True

    return False


def sanitize_next_path(raw: str | None) -> str:
    """
    Sanitize a redirect path to prevent open redirects and nesting loops.

    Rules enforced:
    - Relative-only targets; reject absolute/protocol-relative (http…, //…) → fallback
    - Double-decode max; stop after stability or 2 rounds
    - Remove next from any query string in the final path
    - Blocklist: exact match or prefix match for /login, /v1/auth, /google, /oauth
    - Normalize: drop fragments, collapse repeated slashes (preserve leading /)

    Args:
        raw: Raw path from user input (query param, form, etc.)

    Returns:
        Sanitized path that starts with / and is safe for redirects
    """
    if not raw or not isinstance(raw, str):
        return DEFAULT_REDIRECT

    path = raw.strip()
    if not path:
        return DEFAULT_REDIRECT

    try:
        # Step 1: Safe URL decoding (at most twice)
        path = safe_decode_url(path, max_decodes=2)

        # Step 2: Reject absolute URLs to prevent open redirects
        if path.startswith(("http://", "https://")):
            logger.warning("Rejected absolute URL redirect: %s", path)
            return DEFAULT_REDIRECT

        # Step 3: Reject protocol-relative URLs (starting with // but not ///)
        if path.startswith("//") and not path.startswith("///"):
            logger.warning("Rejected protocol-relative URL redirect: %s", path)
            return DEFAULT_REDIRECT

        # Step 4: Ensure path starts with /
        if not path.startswith("/"):
            logger.warning("Rejected non-relative path redirect: %s", path)
            return DEFAULT_REDIRECT

        # Step 5: Strip fragments (#...)
        if "#" in path:
            path = path.split("#")[0]

        # Step 6: Remove any nested ?next=... parameters
        if "?" in path:
            parsed = urlparse(path)
            query_params = parse_qs(parsed.query)

            # Remove any next parameters
            if "next" in query_params:
                del query_params["next"]

            # Reconstruct path without next params
            if query_params:
                new_query = urlencode(query_params, doseq=True)
                path = f"{parsed.path}?{new_query}"
            else:
                path = parsed.path

        # Step 7: Prevent redirect loops by blocking auth-related paths
        if is_blocklisted_path(path):
            logger.warning("Rejected blocklisted path redirect: %s", path)
            return DEFAULT_REDIRECT

        # Step 8: Normalize redundant slashes
        path = re.sub(r"/+", "/", path)

        # Step 9: Basic path validation (no .. traversal)
        if ".." in path:
            logger.warning("Rejected path traversal redirect: %s", path)
            return DEFAULT_REDIRECT

        return path

    except Exception as e:
        logger.error("Error sanitizing redirect path %s: %s", raw, e)
        return DEFAULT_REDIRECT
