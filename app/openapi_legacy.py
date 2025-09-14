"""
OpenAPI configuration module for GesahniV2.

This module handles OpenAPI tag ordering, route visibility, and schema customization.
"""

import os
from typing import Any

from fastapi.openapi.utils import get_openapi

# Define the exact order of tags as required by tests
TAG_ORDER = ["Care", "Music", "Calendar", "TV", "Admin", "Auth"]

# Hidden routes - these should not appear in OpenAPI docs
HIDDEN_ROUTES = {
    "/docs",
    "/redoc",
    "/openapi.json",
    "/healthz",  # healthz should still be accessible but might be hidden from docs
}


def is_docs_visible() -> bool:
    """Check if docs should be visible based on environment."""
    env = os.getenv("ENV", "dev").strip().lower()
    return env in ["dev"]


def should_hide_route(path: str) -> bool:
    """Check if a route should be hidden from OpenAPI docs."""
    return path in HIDDEN_ROUTES


def customize_openapi_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Customize the OpenAPI schema with proper tag ordering and route filtering.

    Args:
        schema: The raw OpenAPI schema from FastAPI

    Returns:
        Customized OpenAPI schema
    """
    # Filter out hidden routes
    if "paths" in schema:
        filtered_paths = {}
        for path, methods in schema["paths"].items():
            if not should_hide_route(path):
                filtered_paths[path] = methods
        schema["paths"] = filtered_paths

    # Ensure tags are in the correct order
    if "tags" in schema:
        # Create a mapping of tag name to tag info
        tag_map = {tag["name"]: tag for tag in schema["tags"]}

        # Reorder tags according to TAG_ORDER
        ordered_tags = []
        for tag_name in TAG_ORDER:
            if tag_name in tag_map:
                ordered_tags.append(tag_map[tag_name])

        # Add any remaining tags that aren't in TAG_ORDER
        for tag in schema["tags"]:
            if tag["name"] not in TAG_ORDER:
                ordered_tags.append(tag)

        schema["tags"] = ordered_tags

    return schema


def generate_custom_openapi(
    title: str,
    version: str,
    routes: list[Any],
    tags: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Generate a customized OpenAPI schema with proper tag ordering and visibility.

    Args:
        title: API title
        version: API version
        routes: FastAPI routes
        tags: Tag metadata

    Returns:
        Customized OpenAPI schema
    """
    # Generate base schema
    schema = get_openapi(
        title=title,
        version=version,
        routes=routes,
        tags=tags,
    )

    # Apply customizations
    schema = customize_openapi_schema(schema)

    return schema
