"""Environment validation helpers executed during startup."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from app.env_helpers import env_flag

BOOL_TRUE = {"1", "true", "TRUE", "yes", "YES", "on", "ON"}
MASK_KEYS = ("KEY", "SECRET", "TOKEN", "PASSWORD")

REQUIRED_SECRETS = [
    "JWT_SECRET",
    "OPENAI_API_KEY",
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "GOOGLE_CLIENT_SECRET",
    "HOME_ASSISTANT_TOKEN",
]

REQUIRED_CORE = [
    "APP_URL",
    "HOST",
    "PORT",
    "DATABASE_URL",
]

FEATURE_FLAGS = {
    "GSNH_ENABLE_MUSIC": False,
    "GSNH_ENABLE_SPOTIFY": False,
    "GSNH_ENABLE_GOOGLE": False,
    "HOME_ASSISTANT_ENABLED": False,
}

DUPLICATES = [
    # (keep, remove)
    ("GSNH_ENABLE_SPOTIFY", "PROVIDER_SPOTIFY"),
    ("GSNH_ENABLE_SPOTIFY", "SPOTIFY_ENABLED"),
    ("OPENAI_TRANSCRIBE_MODEL", "WHISPER_MODEL"),
]

LEGACY_FLAGS = ["SPOTIFY_ENABLED", "PROVIDER_SPOTIFY", "WHISPER_MODEL"]

logger = logging.getLogger(__name__)


def _mask(key: str, value: str) -> str:
    for frag in MASK_KEYS:
        if frag in key:
            return "***"
    return value


def _is_bool(value: str) -> bool:
    normalized = value.strip()
    lowered = normalized.lower()
    return lowered in {"0", "1", "true", "false", "yes", "no", "on", "off"}


def _is_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


def run_env_doctor() -> None:
    """Validate runtime environment configuration and log problems loudly."""

    problems: list[str] = []
    warnings: list[str] = []

    # 1) Report feature flags
    logger.info("=== INTEGRATION STATUS ===")
    for flag, default in FEATURE_FLAGS.items():
        raw = os.getenv(flag, "1" if default else "0")
        state = "ON ✅" if raw in BOOL_TRUE else "OFF ❌"
        if not _is_bool(raw):
            warnings.append(f"{flag} should be boolean-like (got '{raw}')")
        logger.info("%s: %s", flag, state)
    logger.info("==========================")

    # 2) Detect duplicates/legacy flags
    for keep, remove in DUPLICATES:
        if os.getenv(keep) is not None and os.getenv(remove) is not None:
            warnings.append(f"Duplicate flags: prefer {keep}, remove {remove}")
    for legacy in LEGACY_FLAGS:
        if os.getenv(legacy) is not None:
            warnings.append(f"Legacy env var detected: remove {legacy} (use GSNH_ names)")

    # 3) Required presence
    for key in REQUIRED_CORE:
        if not os.getenv(key):
            problems.append(f"Missing required core var: {key}")
    for key in REQUIRED_SECRETS:
        if not os.getenv(key):
            problems.append(f"Missing required secret: {key}")

    # 4) Placeholder validation
    PLACEHOLDER_VALUES = {
        "SPOTIFY_CLIENT_ID": "REPLACE_WITH_YOUR_SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET": "REPLACE_WITH_YOUR_SPOTIFY_CLIENT_SECRET",
        "GOOGLE_CLIENT_ID": "your-google-client-id",
        "GOOGLE_CLIENT_SECRET": "dev-google-secret",
        "OPENAI_API_KEY": "sk-dev-placeholder",
    }

    for key, placeholder in PLACEHOLDER_VALUES.items():
        value = os.getenv(key, "").strip()
        if value == placeholder:
            problems.append(f"{key} is still set to placeholder value: {placeholder}")

    # 5) URL sanity
    for key in (
        "SPOTIFY_REDIRECT_URI",
        "GOOGLE_REDIRECT_URI",
        "APP_URL",
        "QDRANT_URL",
        "HOME_ASSISTANT_URL",
    ):
        value = os.getenv(key)
        if value:
            if key == "QDRANT_URL" and value.strip() == "":
                continue
            if not _is_url(value):
                warnings.append(f"{key} is not a valid URL: {value}")

    # 5) Ollama consistency
    llama_enabled = env_flag("LLAMA_ENABLED")
    ollama_url = os.getenv("OLLAMA_URL", "")
    if llama_enabled and not ollama_url:
        problems.append("LLAMA_ENABLED=1 but OLLAMA_URL is empty.")
    if not llama_enabled and ollama_url and "bogus-url" in ollama_url:
        warnings.append("OLLAMA_URL looks bogus; clear it when LLAMA is disabled.")

    # 6) CORS checks
    cors = os.getenv("CORS_ALLOW_ORIGINS", "")
    if "localhost:3000" not in cors:
        warnings.append(
            "CORS_ALLOW_ORIGINS does not include http://localhost:3000 (dev UI)."
        )
    if os.getenv("CORS_ALLOW_CREDENTIALS", "").lower() not in {"true", "1"}:
        warnings.append("CORS_ALLOW_CREDENTIALS should be true for cookie auth.")

    # 7) Masked dump of GSNH_ vars
    logger.info("=== GSNH ENV (masked) ===")
    for key, value in sorted(os.environ.items()):
        if key.startswith("GSNH_"):
            logger.info("%s=%s", key, _mask(key, value))
    logger.info("=========================")

    # 8) Final report
    if warnings:
        logger.warning("EnvDoctor warnings:\n- " + "\n- ".join(warnings))
    if problems:
        logger.error("EnvDoctor problems:\n- " + "\n- ".join(problems))
    else:
        logger.info("EnvDoctor: no blocking problems detected ✅")

    # Only refuse to boot in production or when explicitly configured to be strict
    is_production = os.getenv("ENV", "").lower() == "prod"
    should_exit = problems and (is_production or os.getenv("ENFORCE_STRICT_ENV", "").lower() in {"1", "true", "yes"})

    if should_exit:
        raise SystemExit("EnvDoctor found blocking problems. Fix your .env.")
