"""Feature flags for external service dependencies.

Controls which external services are enabled via environment variables.
When disabled, services are skipped at startup and routes return 404.
"""

import os


def _is_on(name: str, default: str = "0") -> bool:
    """Check if an environment variable indicates a feature is enabled."""
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")


# External service feature flags
OLLAMA_ON = _is_on("GSN_ENABLE_OLLAMA", "0")
HA_ON = _is_on("GSN_ENABLE_HOME_ASSISTANT", "0")
QDRANT_ON = _is_on("GSN_ENABLE_QDRANT", "0")

# Security feature flags
SAFE_REDIRECTS_ENFORCED = _is_on("SAFE_REDIRECTS_ENFORCED", "1")

# Risky path feature flags
MUSIC_ENABLED = _is_on("GSN_ENABLE_MUSIC", "0")
AUTH_COOKIES_ENABLED = _is_on("GSN_ENABLE_AUTH_COOKIES", "0")
MODEL_ROUTING_ENABLED = _is_on("GSN_ENABLE_MODEL_ROUTING", "1")

# Legacy compatibility flags (map to new names)
# Support existing OLLAMA_URL presence as implicit enable
if not OLLAMA_ON and os.getenv("OLLAMA_URL"):
    OLLAMA_ON = True

# Support existing HOME_ASSISTANT_TOKEN presence as implicit enable
if not HA_ON and os.getenv("HOME_ASSISTANT_TOKEN"):
    HA_ON = True

# Support existing VECTOR_STORE=qdrant as implicit enable
if not QDRANT_ON and (os.getenv("VECTOR_STORE") or "").lower().startswith("qdrant"):
    QDRANT_ON = True


# Runtime feature flags storage
_runtime_flags = {}


def list_flags() -> dict[str, str]:
    """List all runtime feature flags with their current values."""
    flags = {
        "OLLAMA_ON": str(OLLAMA_ON).lower(),
        "HA_ON": str(HA_ON).lower(),
        "QDRANT_ON": str(QDRANT_ON).lower(),
        "SAFE_REDIRECTS_ENFORCED": str(SAFE_REDIRECTS_ENFORCED).lower(),
        "MUSIC_ENABLED": str(MUSIC_ENABLED).lower(),
        "AUTH_COOKIES_ENABLED": str(AUTH_COOKIES_ENABLED).lower(),
        "MODEL_ROUTING_ENABLED": str(MODEL_ROUTING_ENABLED).lower(),
    }
    # Add runtime flags
    flags.update({k: str(v).lower() for k, v in _runtime_flags.items()})
    return flags


def set_value(key: str, value: str) -> None:
    """Set a runtime feature flag value."""
    _runtime_flags[key] = value


__all__ = [
    "OLLAMA_ON",
    "HA_ON",
    "QDRANT_ON",
    "SAFE_REDIRECTS_ENFORCED",
    "MUSIC_ENABLED",
    "AUTH_COOKIES_ENABLED",
    "MODEL_ROUTING_ENABLED",
    "_is_on",
    "list_flags",
    "set_value",
]
