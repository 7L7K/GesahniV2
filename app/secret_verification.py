"""
Secret verification utilities for FastAPI startup.

This module provides functions to verify that all required secrets and API keys
are properly configured when the application starts up.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Define critical secrets that should be verified
CRITICAL_SECRETS = {
    "JWT_SECRET": {
        "description": "JWT signing secret for authentication",
        "required": True,
        "insecure_defaults": {
            "change-me",
            "default",
            "placeholder",
            "secret",
            "key",
            "",
        },
    },
    "OPENAI_API_KEY": {
        "description": "OpenAI API key for LLM services",
        "required": True,
        "insecure_defaults": {""},
    },
    "HOME_ASSISTANT_TOKEN": {
        "description": "Home Assistant long-lived access token",
        "required": False,
        "insecure_defaults": {""},
    },
    "GOOGLE_CLIENT_SECRET": {
        "description": "Google OAuth client secret",
        "required": False,
        "insecure_defaults": {""},
    },
    "CLERK_SECRET_KEY": {
        "description": "Clerk authentication secret key",
        "required": False,
        "insecure_defaults": {""},
    },
    "SPOTIFY_CLIENT_SECRET": {
        "description": "Spotify API client secret",
        "required": False,
        "insecure_defaults": {""},
    },
    "TWILIO_AUTH_TOKEN": {
        "description": "Twilio authentication token",
        "required": False,
        "insecure_defaults": {""},
    },
}


def verify_secrets_on_boot() -> dict[str, dict[str, str]]:
    """
    Verify all critical secrets on application startup.

    Returns:
        Dict containing verification results for each secret
    """
    # Skip verification during tests for faster test runs
    if _in_test_mode():
        logger.debug("Skipping secret verification in test mode")
        # Return empty results to indicate no verification was performed
        return {}

    results = {}

    for secret_name, config in CRITICAL_SECRETS.items():
        secret_value = os.getenv(secret_name)
        is_set = bool(secret_value)
        is_required = config["required"]

        # Check if using insecure default
        is_insecure = False
        if secret_value and secret_value.strip().lower() in config["insecure_defaults"]:
            is_insecure = True

        # Determine status
        if not is_set:
            if is_required:
                status = "MISSING_REQUIRED"
                logger.error(
                    f"{secret_name}: MISSING (REQUIRED) - {config['description']}"
                )
            else:
                status = "MISSING_OPTIONAL"
        elif is_insecure:
            status = "INSECURE_DEFAULT"
            logger.warning(f"{secret_name}: INSECURE DEFAULT - {config['description']}")
        else:
            status = "SET_SECURE"

        results[secret_name] = {
            "status": status,
            "description": config["description"],
            "required": is_required,
            "is_set": is_set,
            "is_insecure": is_insecure,
        }

    # Additional checks for specific secrets
    _check_openai_key_format(results)
    _check_jwt_secret_strength(results)

    return results


def _check_openai_key_format(results: dict[str, dict[str, str]]) -> None:
    """Check OpenAI API key format."""
    if "OPENAI_API_KEY" in results:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            if openai_key.startswith("sk-"):
                if openai_key.startswith("sk-test"):
                    logger.info("OPENAI_API_KEY: Test key detected")
                    results["OPENAI_API_KEY"]["status"] = "TEST_KEY"
                else:
                    logger.info("OPENAI_API_KEY: Production key format detected")
            else:
                logger.warning(
                    "OPENAI_API_KEY: Unexpected format (should start with 'sk-')"
                )
                results["OPENAI_API_KEY"]["status"] = "INVALID_FORMAT"


def _check_jwt_secret_strength(results: dict[str, dict[str, str]]) -> None:
    """Check JWT secret strength."""
    if "JWT_SECRET" in results:
        jwt_secret = os.getenv("JWT_SECRET")
        if jwt_secret:
            # Basic strength check - only update status if not already flagged as insecure
            if len(jwt_secret) < 32 and results["JWT_SECRET"]["status"] not in [
                "INSECURE_DEFAULT",
                "MISSING_REQUIRED",
            ]:
                logger.warning("JWT_SECRET: Weak secret (less than 32 characters)")
                results["JWT_SECRET"]["status"] = "WEAK_SECRET"
            elif len(jwt_secret) >= 64:
                logger.info("JWT_SECRET: Strong secret (64+ characters)")


def _in_test_mode() -> bool:
    """Detect test mode similar to other modules so tests can run with weaker secrets."""

    def v(s):
        return str(os.getenv(s, "")).strip().lower()

    env = v("ENV")
    dev_mode = v("DEV_MODE") in {"1", "true", "yes", "on"}
    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("PYTEST_RUNNING")
        or v("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or env == "test"
        or env == "dev"  # Allow dev mode to use weak secrets
        or dev_mode  # Allow DEV_MODE=1 to use weak secrets
    )


def get_missing_required_secrets() -> list[str]:
    """Get list of missing required secrets."""
    results = verify_secrets_on_boot()
    return [
        secret_name
        for secret_name, result in results.items()
        if result["status"] == "MISSING_REQUIRED"
    ]


def get_insecure_secrets() -> list[str]:
    """Get list of secrets using insecure defaults."""
    results = verify_secrets_on_boot()
    return [
        secret_name
        for secret_name, result in results.items()
        if result["status"]
        in ["INSECURE_DEFAULT", "WEAK_SECRET", "INVALID_FORMAT", "TEST_KEY"]
    ]


def audit_prod_env() -> None:
    """Strict production environment audit - refuse placeholder values in prod."""
    env = os.getenv("ENV", "dev").lower()
    dev_mode = os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}

    # Only run strict checks in production (not dev mode)
    if env in {"prod", "production"} and not dev_mode:
        logger.info("Running strict production environment audit")

        # JWT_SECRET is mandatory and must be strong
        jwt_secret = os.getenv("JWT_SECRET", "")
        if not jwt_secret:
            raise RuntimeError("Missing required env: JWT_SECRET")
        if len(jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET too weak (need >=32 bytes)")

        # OpenAI API key validation
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            if openai_key.startswith("sk-test"):
                raise RuntimeError("OPENAI_API_KEY: Test key not allowed in production")
            if openai_key in {"test", "fake", "placeholder", "change-me"}:
                raise RuntimeError(
                    "OPENAI_API_KEY: Placeholder value not allowed in production"
                )

        # Feature-gated requirements
        if os.getenv("OTEL_ENABLED", "0").lower() in {"1", "true", "yes", "on"}:
            otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
            if not otel_endpoint:
                raise RuntimeError(
                    "Missing required env: OTEL_EXPORTER_OTLP_ENDPOINT (OTEL_ENABLED=1)"
                )

        # OAuth credentials if enabled
        if os.getenv("ENABLE_GOOGLE_AUTH", "1").lower() in {"1", "true", "yes", "on"}:
            google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
            google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
            if not google_client_id:
                raise RuntimeError(
                    "Missing required env: GOOGLE_CLIENT_ID (Google auth enabled)"
                )
            if not google_client_secret:
                raise RuntimeError(
                    "Missing required env: GOOGLE_CLIENT_SECRET (Google auth enabled)"
                )

        # CORS configuration
        cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "")
        if not cors_origins:
            raise RuntimeError("CORS_ALLOW_ORIGINS required in production")

        # Apple OAuth if enabled
        if os.getenv("ENABLE_APPLE_AUTH", "0").lower() in {"1", "true", "yes", "on"}:
            apple_client_id = os.getenv("APPLE_CLIENT_ID", "")
            if not apple_client_id:
                raise RuntimeError(
                    "Missing required env: APPLE_CLIENT_ID (Apple auth enabled)"
                )

        # Vector store configuration
        vector_store = os.getenv("VECTOR_STORE", "chroma").lower()
        if vector_store == "qdrant":
            qdrant_url = os.getenv("QDRANT_URL", "")
            if not qdrant_url:
                raise RuntimeError(
                    "Missing required env: QDRANT_URL (VECTOR_STORE=qdrant)"
                )
        elif vector_store == "chroma":
            chroma_path = os.getenv("CHROMA_PATH", "")
            if not chroma_path:
                logger.warning("CHROMA_PATH not set - using default path")

        logger.info("✅ Production environment audit passed")
    else:
        logger.debug("Skipping production audit (dev mode or non-prod environment)")


def log_secret_summary() -> None:
    """Log a summary of secret verification results."""
    results = verify_secrets_on_boot()

    missing_required = get_missing_required_secrets()
    insecure = get_insecure_secrets()

    if missing_required:
        logger.error(f"Missing required secrets: {', '.join(missing_required)}")

    if insecure:
        logger.warning(f"Secrets with security issues: {', '.join(insecure)}")

    if not missing_required and not insecure:
        logger.debug("All critical secrets are properly configured")
    # Fail fast for missing or weak JWT secret in non-test environments
    try:
        jwt_res = results.get("JWT_SECRET")
        if jwt_res:
            status = jwt_res.get("status")
            if not _in_test_mode() and status in {
                "MISSING_REQUIRED",
                "WEAK_SECRET",
                "INSECURE_DEFAULT",
            }:
                # Raise a clear error to stop startup
                raise RuntimeError("JWT_SECRET too weak (need >=32 bytes)")
    except RuntimeError:
        raise
    except Exception:
        # Defensive: don't crash startup on unexpected checks
        pass
