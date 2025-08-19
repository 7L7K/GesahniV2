"""
Secret verification utilities for FastAPI startup.

This module provides functions to verify that all required secrets and API keys
are properly configured when the application starts up.
"""

import os
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Define critical secrets that should be verified
CRITICAL_SECRETS = {
    "JWT_SECRET": {
        "description": "JWT signing secret for authentication",
        "required": True,
        "insecure_defaults": {"change-me", "default", "placeholder", "secret", "key", ""}
    },
    "OPENAI_API_KEY": {
        "description": "OpenAI API key for LLM services",
        "required": True,
        "insecure_defaults": {""}
    },
    "HOME_ASSISTANT_TOKEN": {
        "description": "Home Assistant long-lived access token",
        "required": False,
        "insecure_defaults": {""}
    },
    "GOOGLE_CLIENT_SECRET": {
        "description": "Google OAuth client secret",
        "required": False,
        "insecure_defaults": {""}
    },
    "CLERK_SECRET_KEY": {
        "description": "Clerk authentication secret key",
        "required": False,
        "insecure_defaults": {""}
    },
    "SPOTIFY_CLIENT_SECRET": {
        "description": "Spotify API client secret",
        "required": False,
        "insecure_defaults": {""}
    },
    "TWILIO_AUTH_TOKEN": {
        "description": "Twilio authentication token",
        "required": False,
        "insecure_defaults": {""}
    }
}

def verify_secrets_on_boot() -> Dict[str, Dict[str, str]]:
    """
    Verify all critical secrets on application startup.
    
    Returns:
        Dict containing verification results for each secret
    """
    logger.info("=== SECRET USAGE VERIFICATION ON BOOT ===")
    
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
                logger.error(f"{secret_name}: MISSING (REQUIRED) - {config['description']}")
            else:
                status = "MISSING_OPTIONAL"
                logger.info(f"{secret_name}: NOT SET (optional) - {config['description']}")
        elif is_insecure:
            status = "INSECURE_DEFAULT"
            logger.warning(f"{secret_name}: INSECURE DEFAULT - {config['description']}")
        else:
            status = "SET_SECURE"
            logger.info(f"{secret_name}: SET - {config['description']}")
        
        results[secret_name] = {
            "status": status,
            "description": config["description"],
            "required": is_required,
            "is_set": is_set,
            "is_insecure": is_insecure
        }
    
    # Additional checks for specific secrets
    _check_openai_key_format(results)
    _check_jwt_secret_strength(results)
    
    logger.info("=== END SECRET VERIFICATION ===")
    return results

def _check_openai_key_format(results: Dict[str, Dict[str, str]]) -> None:
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
                logger.warning("OPENAI_API_KEY: Unexpected format (should start with 'sk-')")
                results["OPENAI_API_KEY"]["status"] = "INVALID_FORMAT"

def _check_jwt_secret_strength(results: Dict[str, Dict[str, str]]) -> None:
    """Check JWT secret strength."""
    if "JWT_SECRET" in results:
        jwt_secret = os.getenv("JWT_SECRET")
        if jwt_secret:
            # Basic strength check - only update status if not already flagged as insecure
            if len(jwt_secret) < 32 and results["JWT_SECRET"]["status"] not in ["INSECURE_DEFAULT", "MISSING_REQUIRED"]:
                logger.warning("JWT_SECRET: Weak secret (less than 32 characters)")
                results["JWT_SECRET"]["status"] = "WEAK_SECRET"
            elif len(jwt_secret) >= 64:
                logger.info("JWT_SECRET: Strong secret (64+ characters)")

def get_missing_required_secrets() -> List[str]:
    """Get list of missing required secrets."""
    results = verify_secrets_on_boot()
    return [
        secret_name for secret_name, result in results.items()
        if result["status"] == "MISSING_REQUIRED"
    ]

def get_insecure_secrets() -> List[str]:
    """Get list of secrets using insecure defaults."""
    results = verify_secrets_on_boot()
    return [
        secret_name for secret_name, result in results.items()
        if result["status"] in ["INSECURE_DEFAULT", "WEAK_SECRET", "INVALID_FORMAT", "TEST_KEY"]
    ]

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
        logger.info("All critical secrets are properly configured")
