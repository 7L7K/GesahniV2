"""OpenAPI schema generation - isolated from router modules.

This module handles OpenAPI schema generation without importing any
router modules that could create circular dependencies.
"""
from typing import Any, Dict, List


def generate_custom_openapi(
    title: str,
    version: str,
    routes: List[Any],
    tags: List[Dict[str, Any]],
    description: str = "GesahniV2 API",
) -> Dict[str, Any]:
    """Generate custom OpenAPI schema.

    This function generates the OpenAPI schema without importing
    any router modules, avoiding circular dependencies.

    Args:
        title: API title
        version: API version
        routes: FastAPI routes
        tags: OpenAPI tags
        description: API description

    Returns:
        OpenAPI schema dictionary
    """
    from fastapi.openapi.utils import get_openapi

    # Generate base OpenAPI schema
    schema = get_openapi(
        title=title,
        version=version,
        description=description,
        routes=routes,
        tags=tags,
    )

    # Add custom schema modifications here if needed
    # For example, custom examples, descriptions, etc.

    # Add security schemes if needed
    if "components" not in schema:
        schema["components"] = {}

    if "securitySchemes" not in schema["components"]:
        schema["components"]["securitySchemes"] = {}

    # Add Bearer token security scheme
    schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    # Add global security if needed
    if "security" not in schema:
        schema["security"] = []

    # Note: We don't add global security here to avoid affecting all endpoints
    # Individual routes should define their own security requirements

    return schema


def setup_openapi_for_app(app: Any) -> None:
    """Set up OpenAPI generation for a FastAPI app.

    This function should be called from create_app() to set up
    OpenAPI generation without triggering router imports.

    Args:
        app: FastAPI application instance
    """
    # Import tags metadata (should be lightweight)
    try:
        from ..main import tags_metadata
    except ImportError:
        # Fallback if import fails
        tags_metadata = []

    def _custom_openapi():
        """Custom OpenAPI generator."""
        if app.openapi_schema:
            return app.openapi_schema

        # Import config only when needed
        try:
            from ..config_docs import should_show_servers, get_dev_servers
        except ImportError:
            should_show_servers = lambda: False
            get_dev_servers = lambda: []

        schema = generate_custom_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
            tags=tags_metadata,
        )

        # Provide developer-friendly servers list in dev
        if should_show_servers():
            servers = get_dev_servers()
            if servers:
                schema["servers"] = [{"url": url} for url in servers]

        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = _custom_openapi  # type: ignore[assignment]
