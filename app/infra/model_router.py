"""Model router infrastructure component.

This module manages the global model router singleton.
Initialized from create_app() to avoid circular dependencies.
"""

from ..router.model_router import ModelRouter

_model_router: ModelRouter | None = None


def init_model_router() -> None:
    """Initialize the global model router singleton.

    This function should be called from create_app() to initialize
    the model router singleton.
    """
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()


def get_model_router() -> ModelRouter:
    """Get the global model router singleton.

    Returns:
        The global model router instance

    Raises:
        RuntimeError: If the model router has not been initialized
    """
    if _model_router is None:
        raise RuntimeError(
            "Model router has not been initialized. Call init_model_router() first."
        )
    return _model_router
