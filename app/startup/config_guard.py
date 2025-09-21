"""
Production configuration guardrails - refuses risky configs in prod environment.
"""

import logging
import os

log = logging.getLogger(__name__)


def _is_truthy(v):
    """Check if a string value represents truthy."""
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    """Configuration error that should prevent application startup."""

    pass


def assert_strict_prod():
    """
    Assert strict production configuration requirements.

    Only runs when ENV=prod/production and DEV_MODE is not enabled.
    Raises ConfigError if any production requirements are not met.
    """
    env = (os.getenv("ENV") or "dev").strip().lower()
    dev_mode = _is_truthy(os.getenv("DEV_MODE"))

    # Only enforce strict checks in production when not in dev mode
    if env not in {"prod", "production"} or dev_mode:
        log.debug("Skipping strict prod guards: env=%s dev_mode=%s", env, dev_mode)
        return

    log.info("🔒 Enforcing strict production configuration guardrails")

    # 1) JWT secret length (must be >=32 characters for security)
    sec = os.getenv("JWT_SECRET", "")
    if len(sec) < 32:
        raise ConfigError("JWT_SECRET too weak in prod: must be >=32 characters")

    # 2) Cookies must be secure/samesite+strict in prod
    if not _is_truthy(os.getenv("COOKIES_SECURE", "1")):
        raise ConfigError("COOKIES_SECURE must be enabled in prod")

    cookies_samesite = os.getenv("COOKIES_SAMESITE", "strict").lower()
    if cookies_samesite != "strict":
        raise ConfigError("COOKIES_SAMESITE must be 'strict' in prod")

    # 3) Optional routers must be explicitly enabled (no surprises)
    optional_flags = {
        "GSNH_ENABLE_SPOTIFY": ["SPOTIFY_ENABLED"],
        "APPLE_OAUTH_ENABLED": [],
        "DEVICE_AUTH_ENABLED": [],
    }
    for flag, legacy_flags in optional_flags.items():
        value = os.getenv(flag)
        if value is None:
            for legacy in legacy_flags:
                legacy_value = os.getenv(legacy)
                if legacy_value is not None:
                    log.warning(
                        "Legacy env var in prod: %s (prefer %s)", legacy, flag
                    )
                    value = legacy_value
                    break
        v = value or "0"
        # We don't raise errors here, just log for awareness
        # The requirement is explicit intention, not necessarily enabled
        if _is_truthy(v):
            log.info("Optional integration enabled in prod: %s=%s", flag, v)

    # 4) Tracing & request IDs required to correlate prod incidents
    if not _is_truthy(os.getenv("REQ_ID_ENABLED", "1")):
        raise ConfigError("REQ_ID_ENABLED must be on in prod")

    # Additional production safety checks
    if not _is_truthy(os.getenv("LOG_LEVEL")):
        # Default to INFO if not set, but warn about missing explicit config
        log.warning("LOG_LEVEL not explicitly set in prod - defaulting to INFO")

    # Check for debug mode flags that shouldn't be on in prod
    debug_flags = ["DEBUG", "DEBUG_MODEL_ROUTING"]
    for flag in debug_flags:
        if _is_truthy(os.getenv(flag)):
            log.warning(
                "Debug flag enabled in prod: %s - consider disabling for security", flag
            )

    log.info("✅ All production configuration guardrails passed")


def assert_demo_not_in_prod() -> None:
    """Refuse to start if DEMO_MODE=1 in production."""
    env = os.getenv("ENV", "dev").lower()
    demo = os.getenv("DEMO_MODE", "0")
    log.info(f"🔍 DEMO GUARD: Checking demo mode - env={env}, demo_mode={demo}")

    if env in {"prod", "production"} and demo == "1":
        msg = "Refusing to start: DEMO_MODE=1 in production"
        log.critical(f"🚫 {msg}")
        sys.exit(msg)

    if demo == "1":
        log.info("🎭 DEMO MODE: Demo mode is ENABLED")
    else:
        log.debug("🔓 DEMO MODE: Demo mode is DISABLED")
