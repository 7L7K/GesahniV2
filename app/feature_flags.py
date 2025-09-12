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


__all__ = ["OLLAMA_ON", "HA_ON", "QDRANT_ON", "_is_on"]