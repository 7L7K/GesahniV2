#!/usr/bin/env python3
"""
JWT Configuration Inspector

Prints current JWT configuration without starting the full application.
Shows algorithm, key length, key type, and security status.
"""

import os
import sys
import re
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import environment loading and JWT config
from app.env_utils import load_env

_PLACEHOLDER_PAT = re.compile(r"your[-_ ]secure[-_ ]jwt[-_ ]secret|placeholder|changeme", re.I)

def analyze_jwt_config() -> dict:
    """Analyze JWT configuration for security issues."""
    try:
        # Import directly from jwt_config to avoid circular imports
        from app.security.jwt_config import get_jwt_config

        # Try to load config (may fail if secrets are invalid)
        cfg = get_jwt_config(allow_dev_weak=True)

        issues = []

        # Check for placeholder patterns in HS256 secret
        if cfg.alg == "HS256" and cfg.secret:
            if len(cfg.secret) < 32:
                issues.append("Secret too short (<32 chars)")
            if _PLACEHOLDER_PAT.search(cfg.secret):
                issues.append("Contains placeholder text - change for production")
            if re.fullmatch(r"(dev|staging|prod|test|secret|token)[-_]?\d*", cfg.secret, re.I):
                issues.append("Looks like a low-entropy label - use a random value")

        # Check RSA/EC keys
        elif cfg.alg in ("RS256", "ES256"):
            if not cfg.private_keys or not cfg.public_keys:
                issues.append("Missing private/public key pair")
            elif set(cfg.private_keys.keys()) != set(cfg.public_keys.keys()):
                issues.append("Mismatched private/public key pairs")

        status = "SECURE" if not issues else "INSECURE"

        return {
            "status": status,
            "issues": issues,
            "config": cfg
        }

    except RuntimeError as e:
        return {
            "status": "ERROR",
            "issues": [str(e)],
            "config": None
        }
    except Exception as e:
        return {
            "status": "UNKNOWN",
            "issues": [f"Failed to load config: {e}"],
            "config": None
        }

def main():
    """Main function to inspect JWT configuration."""
    print("🔐 JWT Configuration Inspector")
    print("=" * 50)

    # Load environment (same as the app does)
    load_env()

    # Get algorithm from environment (even if config loading fails)
    jwt_algs = os.getenv("JWT_ALGS", "HS256")
    algorithm = jwt_algs.split(",")[0].strip() if jwt_algs else "HS256"
    print(f"Algorithm: {algorithm}")

    # Analyze JWT configuration
    analysis = analyze_jwt_config()

    if analysis["config"]:
        cfg = analysis["config"]

        if cfg.alg == "HS256":
            key_type = "HMAC"
            key_length = f"{len(cfg.secret)} chars" if cfg.secret else "N/A"
        else:
            key_type = "RSA/EC"
            key_length = f"{len(cfg.private_keys)} keys" if cfg.private_keys else "N/A"

        print(f"Key Type:  {key_type}")
        print(f"Key Length: {key_length}")
    else:
        # Show algorithm but indicate config issues
        print("Key Type:  Unknown")
        print("Key Length: N/A")

    print(f"Security:  {analysis['status']}")

    if analysis['issues']:
        print("Issues:")
        for issue in analysis['issues']:
            print(f"  ❌ {issue}")
    else:
        print("✅ No security issues detected")

    # Additional configuration
    print("\nAdditional JWT Configuration:")
    jwt_iss = os.getenv("JWT_ISS", "")
    jwt_aud = os.getenv("JWT_AUD", "")
    jwt_expire = os.getenv("JWT_EXPIRE_MINUTES", "30")
    jwt_refresh = os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440")

    if jwt_iss:
        print(f"Issuer: {jwt_iss}")
    if jwt_aud:
        print(f"Audience: {jwt_aud}")

    print(f"Access TTL: {jwt_expire} minutes")
    print(f"Refresh TTL: {jwt_refresh} minutes")

    # Environment context
    env = os.getenv("ENV", "unknown")
    dev_mode = os.getenv("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}

    print("\nEnvironment Context:")
    print(f"ENV:        {env}")
    print(f"DEV_MODE:   {'Enabled' if dev_mode else 'Disabled'}")

    if dev_mode and analysis.get('status') == 'INSECURE':
        print("⚠️  DEV_MODE allows insecure secrets - not recommended for production")

    # Test mode detection
    test_mode = (
        os.getenv("PYTEST_RUNNING") or
        os.getenv("PYTEST_CURRENT_TEST") or
        os.getenv("ENV", "").strip().lower() == "test"
    )

    if test_mode:
        print("🧪 Test mode detected")

if __name__ == "__main__":
    main()
