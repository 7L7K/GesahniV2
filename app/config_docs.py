"""
Documentation configuration for GesahniV2 API.

This module provides visibility flags and configuration for API documentation.
"""
import os
from typing import Dict, Any


def get_docs_visibility_config() -> Dict[str, Any]:
    """
    Get documentation visibility configuration based on environment.

    Returns:
        Dict containing visibility configuration for docs, redoc, and openapi.json
    """
    env = os.getenv("ENV", "dev").strip().lower()

    # In development environment, show all documentation
    if env == "dev":
        return {
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
            "docs_visible": True,
        }

    # In production and staging, hide documentation
    return {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
        "docs_visible": False,
    }


def get_swagger_ui_parameters() -> Dict[str, Any]:
    """
    Get Swagger UI parameters for better developer experience.

    Returns:
        Dict containing Swagger UI configuration parameters
    """
    return {
        "persistAuthorization": True,
        "docExpansion": "list",
        "filter": True,
    }


def should_show_servers() -> bool:
    """
    Check if servers should be shown in OpenAPI schema.

    Returns:
        True if servers should be included, False otherwise
    """
    env = os.getenv("ENV", "dev").strip().lower()
    return env == "dev"


def get_dev_servers() -> list[str]:
    """
    Get list of development servers for OpenAPI schema.

    Returns:
        List of server URLs for development environment
    """
    servers_env = os.getenv("OPENAPI_DEV_SERVERS", "http://localhost:8000")
    if servers_env:
        return [s.strip() for s in servers_env.split(",") if s.strip()]
    return ["http://localhost:8000"]
