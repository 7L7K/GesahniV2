"""
Secure module loader with allowlist validation.

This module provides secure alternatives to __import__ for dynamic module loading,
preventing code injection attacks by validating module paths against allowlists.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

log = logging.getLogger(__name__)

# Allowlist of safe standard library modules
SAFE_STDLIB_MODULES = frozenset(
    {
        "logging",
        "json",
        "hashlib",
        "time",
        "datetime",
        "pathlib",
        "os",  # Limited use for environment variables only
        "sys",  # Limited use for system info
    }
)

# Allowlist of safe module prefixes for router loading
SAFE_ROUTER_MODULES = (
    frozenset(
        {
            "app.api.",
            "app.router.",
            "app.routers.",
            "app.status",
            "app.skills.",
            "app.auth.",  # For auth endpoints and related modules
            "app.auth_device",
            "app.api.auth_router_dev",
            "app.integrations.",  # For integration modules
            "app.security.",  # For security utilities
        }
    )
    | SAFE_STDLIB_MODULES
)

# Allowlist of safe module prefixes for general utility loading
SAFE_UTILITY_MODULES = (
    frozenset(
        {
            "app.gpt_client",
            "app.transcription",
            "app.deps.scheduler",
            "app.router.alias_api",
            "app.security.",  # For security utilities
        }
    )
    | SAFE_STDLIB_MODULES
)

# Combined allowlist for all dynamic loading
SAFE_MODULES = SAFE_ROUTER_MODULES | SAFE_UTILITY_MODULES


def _is_module_allowed(module_path: str, allowlist: frozenset[str]) -> bool:
    """Check if a module path is in the allowlist."""
    # Exact match for modules without submodules
    if module_path in allowlist:
        return True

    # Prefix match for submodules (e.g., "app.api.auth" matches "app.api.")
    for allowed_prefix in allowlist:
        if module_path.startswith(allowed_prefix):
            return True

    return False


def secure_import_module(
    module_path: str, allowlist: frozenset[str] | None = None
) -> Any:
    """
    Securely import a module with allowlist validation.

    Args:
        module_path: The module path to import (e.g., "app.api.auth")
        allowlist: Custom allowlist, or None to use default SAFE_MODULES

    Returns:
        The imported module

    Raises:
        ValueError: If module_path is not in allowlist
        ImportError: If module cannot be imported
    """
    if allowlist is None:
        allowlist = SAFE_MODULES

    if not _is_module_allowed(module_path, allowlist):
        log.error("Blocked attempt to import unauthorized module: %s", module_path)
        raise ValueError(f"Module '{module_path}' is not in the allowlist")

    try:
        return importlib.import_module(module_path)
    except ImportError as e:
        log.error("Failed to import module %s: %s", module_path, e)
        raise


def secure_import_attr(
    module_path: str, attr_name: str, allowlist: frozenset[str] | None = None
) -> Any:
    """
    Securely import a module and get an attribute from it.

    Args:
        module_path: The module path to import
        attr_name: The attribute name to retrieve
        allowlist: Custom allowlist, or None to use default SAFE_MODULES

    Returns:
        The requested attribute

    Raises:
        ValueError: If module_path is not in allowlist
        ImportError: If module cannot be imported
        AttributeError: If attribute does not exist
    """
    module = secure_import_module(module_path, allowlist)

    try:
        return getattr(module, attr_name)
    except AttributeError as e:
        log.error(
            "Attribute '%s' not found in module '%s': %s", attr_name, module_path, e
        )
        raise


def secure_load_router(import_path: str) -> Any:
    """
    Securely load a router from a module:attribute path.

    Args:
        import_path: Path in format "module.path:attribute_name"

    Returns:
        The router object

    Raises:
        ValueError: If path format is invalid or module not allowed
    """
    try:
        module_path, attr_name = import_path.split(":", 1)
    except ValueError:
        raise ValueError(
            f"Invalid import path format: {import_path} (expected 'module:attribute')"
        )

    return secure_import_attr(module_path, attr_name, SAFE_ROUTER_MODULES)


def secure_load_callable(import_path: str) -> Any:
    """
    Securely load a callable from a module:attribute path for utility functions.

    Args:
        import_path: Path in format "module.path:attribute_name"

    Returns:
        The callable object

    Raises:
        ValueError: If path format is invalid or module not allowed
    """
    try:
        module_path, attr_name = import_path.split(":", 1)
    except ValueError:
        raise ValueError(
            f"Invalid import path format: {import_path} (expected 'module:attribute')"
        )

    return secure_import_attr(module_path, attr_name, SAFE_UTILITY_MODULES)
