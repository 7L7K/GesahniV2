"""
CORS configuration settings for GesahniV2.

This module contains CORS configuration logic separate from the middleware implementation.
Handles origin parsing, validation, and settings management.
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def get_cors_origins() -> list[str]:
    """Get the configured CORS allowed origins."""
    # In dev environment, disable CORS for same-origin requests (non-negotiable)
    env = os.getenv("ENV", "dev").strip().lower()
    if env == "dev":
        return []

    # In dev proxy mode, disable CORS for same-origin requests
    if os.getenv("NEXT_PUBLIC_USE_DEV_PROXY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return []

    cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")

    # If the Next dev proxy is enabled, be explicit and allow both localhost
    # variants so local tooling (127.0.0.1 vs localhost) can work reliably.
    try:
        if os.getenv("USE_DEV_PROXY", "").strip().lower() in {"1", "true", "yes", "on"}:
            # Prepend both canonical frontend origins if not already present
            if "http://127.0.0.1:3000" not in cors_origins:
                cors_origins = cors_origins + ",http://127.0.0.1:3000"
            if "http://localhost:3000" not in cors_origins:
                cors_origins = cors_origins + ",http://localhost:3000"
    except Exception:
        pass

    # Parse and normalize entries
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

    # Normalize common localhost variants (127.0.0.1 -> localhost)
    origins = [
        o.replace("http://127.0.0.1:", "http://localhost:").replace(
            "https://127.0.0.1:", "https://localhost:"
        )
        for o in origins
    ]

    # Remove any literal 'null' tokens (case-insensitive)
    origins = [o for o in origins if o and o.lower() != "null"]

    # Strict sanitization: prefer the single canonical localhost origin when
    # any localhost-style origin is present; otherwise, strip obvious
    # unwanted entries (raw IPs and common non-frontend ports like 8080).

    sanitized = []
    found_localhost = False
    for o in origins:
        try:
            p = urlparse(o)
            host = p.hostname or ""
            port = p.port
            scheme = p.scheme or "http"

            # Map any localhost or 127.0.0.1 entry to the canonical frontend origin
            if host in ("localhost", "127.0.0.1"):
                if port is None or port == 3000 or scheme == "http":
                    found_localhost = True
                    continue

            # Skip raw IP addresses (e.g. 10.0.0.138) to avoid leaking LAN IPs
            if re.match(r"^\d+(?:\.\d+){3}$", host):
                continue

            # Skip alternate common dev ports that are not the frontend (e.g. :8080)
            if port == 8080:
                continue

            # Keep everything else (likely legitimate production origins)
            sanitized.append(o)
        except Exception:
            # If unparsable, drop it
            continue

    if found_localhost:
        origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]
    else:
        # Deduplicate but preserve order-ish
        seen = set()
        out = []
        for o in sanitized:
            if o in seen:
                continue
            seen.add(o)
            out.append(o)
        origins = out or ["http://localhost:3000"]

    if not origins:
        logger.warning(
            "No CORS origins configured. Defaulting to http://localhost:3000"
        )
        origins = ["http://localhost:3000"]

    return origins


def get_cors_allow_credentials() -> bool:
    """Get the CORS allow credentials setting."""
    return True  # Always allow credentials for local dev and cookie support


def get_cors_allow_methods() -> list[str]:
    """Get the CORS allowed methods."""
    return ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def get_cors_allow_headers() -> list[str]:
    """Get the CORS allowed headers."""
    return ["*", "Authorization"]


def get_cors_expose_headers() -> list[str]:
    """Get the CORS exposed headers."""
    return ["X-Request-ID", "X-Error-Code", "X-Error-ID", "X-Trace-ID"]


def get_cors_max_age() -> int:
    """Get the CORS max age for preflight caching."""
    return 600


def validate_cors_origins(origins: list[str]) -> bool:
    """Validate that all origins are in the same address family."""
    if not origins:
        return True

    localhost_count = sum(1 for o in origins if "localhost" in o or "127.0.0.1" in o)
    ip_count = sum(1 for o in origins if "localhost" not in o and "127.0.0.1" not in o)

    same_family = localhost_count == 0 or ip_count == 0

    if not same_family:
        logger.warning(
            "Mixed address families detected in CORS origins (post-sanitize)."
        )
        logger.warning(
            "This may cause WebSocket connection issues. Consider using consistent addressing."
        )

    return same_family


__all__ = [
    "get_cors_origins",
    "get_cors_allow_credentials",
    "get_cors_allow_methods",
    "get_cors_allow_headers",
    "get_cors_expose_headers",
    "get_cors_max_age",
    "validate_cors_origins",
]
