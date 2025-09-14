"""Dependencies for feature flag enforcement.

Provides FastAPI dependencies that check feature flags and return 404
when external services are disabled via environment variables.
"""

from fastapi import HTTPException, status

from app.feature_flags import HA_ON, OLLAMA_ON, QDRANT_ON


def require_feature(name: str):
    """Return a dependency that enforces feature flag for external services.

    Args:
        name: Feature name ("ollama", "home_assistant", "qdrant")

    Returns:
        FastAPI dependency that raises 404 if feature is disabled

    Usage:
        @router.get("/llama/status", dependencies=[Depends(require_feature("ollama"))])
        async def llama_status(): ...
    """

    async def _dep() -> None:
        feature_map = {
            "ollama": OLLAMA_ON,
            "home_assistant": HA_ON,
            "qdrant": QDRANT_ON,
        }

        enabled = feature_map.get(name, False)
        if not enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Feature {name} disabled"
            )

    return _dep


# Convenience dependencies for common features
require_ollama = require_feature("ollama")
require_home_assistant = require_feature("home_assistant")
require_qdrant = require_feature("qdrant")


__all__ = [
    "require_feature",
    "require_ollama",
    "require_home_assistant",
    "require_qdrant",
]
