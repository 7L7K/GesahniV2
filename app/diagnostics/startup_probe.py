from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI


def _redact_by_length(value: str, max_visible: int = 4) -> str:
    """Redact sensitive values by showing only first N characters."""
    if len(value) <= max_visible:
        return value
    return value[:max_visible] + "*" * (len(value) - max_visible)


def _get_env_snapshot() -> dict[str, str]:
    """Get environment variables snapshot with sensitive values redacted."""
    # List of environment variables that might contain secrets
    sensitive_vars = {
        "OPENAI_API_KEY",
        "JWT_SECRET",
        "JWT_REFRESH_SECRET",
        "HOME_ASSISTANT_TOKEN",
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "SPOTIFY_REFRESH_TOKEN",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "APPLE_CLIENT_ID",
        "APPLE_CLIENT_SECRET",
        "APPLE_PRIVATE_KEY",
        "ADMIN_TOKEN",
        "API_TOKEN",
        "QDRANT_API_KEY",
        "RAGFLOW_API_KEY",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_ACCOUNT_SID",
    }

    snapshot = {}
    for key, value in os.environ.items():
        if key in sensitive_vars:
            snapshot[key] = _redact_by_length(value)
        else:
            snapshot[key] = value

    return snapshot


def _get_package_versions() -> dict[str, str]:
    """Get versions for key packages used in the application."""
    packages = ["fastapi", "uvicorn", "pydantic", "qdrant_client", "openai"]
    versions = {}

    for package in packages:
        try:
            if package == "fastapi":
                import fastapi

                versions[package] = fastapi.__version__
            elif package == "uvicorn":
                import uvicorn

                versions[package] = uvicorn.__version__
            elif package == "pydantic":
                import pydantic

                versions[package] = pydantic.VERSION
            elif package == "qdrant_client":
                try:
                    import qdrant_client  # type: ignore

                    versions[package] = getattr(qdrant_client, "__version__", "unknown")
                except ImportError:
                    versions[package] = "not installed"
            elif package == "openai":
                try:
                    import openai  # type: ignore

                    versions[package] = openai.__version__
                except ImportError:
                    versions[package] = "not installed"
        except ImportError:
            versions[package] = "not installed"

    return versions


def _get_routes_info(app: FastAPI) -> list[dict[str, Any]]:
    """Extract route information from FastAPI app."""
    routes_info = []
    for route in app.routes:
        route_info = {
            "path": getattr(route, "path", str(route)),
            "name": getattr(route, "name", ""),
            "methods": getattr(route, "methods", set()),
            "endpoint_name": getattr(getattr(route, "endpoint", None), "__name__", ""),
            "include_in_schema": getattr(route, "include_in_schema", True),
        }
        routes_info.append(route_info)
    return routes_info


def _get_middleware_info(app: FastAPI) -> list[dict[str, Any]]:
    """Extract middleware information from FastAPI app."""
    middleware_info = []
    for middleware in app.user_middleware:
        middleware_info.append(
            {
                "class_name": middleware.cls.__name__,
                "options": getattr(middleware, "options", {}),
            }
        )
    return middleware_info


def _route_dump(app) -> List[Dict[str, Any]]:
    out = []
    for r in app.routes:
        out.append(
            {
                "path": getattr(r, "path", None),
                "name": getattr(r, "name", None),
                "methods": sorted(getattr(r, "methods", []) or []),
                "endpoint": getattr(getattr(r, "endpoint", None), "__name__", None),
                "include_in_schema": getattr(r, "include_in_schema", None),
            }
        )
    out.sort(key=lambda x: (x.get("path") or "", ",".join(x.get("methods") or [])))
    return out


def _middleware_dump(app) -> List[Dict[str, Any]]:
    out = []
    for m in getattr(app, "user_middleware", []):
        out.append(
            {
                "cls": getattr(m, "cls", type(m)).__name__,
                "options": getattr(m, "options", {}),
            }
        )
    return out


def _module_versions(names: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for n in names:
        try:
            mod = importlib.import_module(n)
            ver = getattr(mod, "__version__", None) or getattr(mod, "VERSION", None)
            out[n] = str(ver)
        except Exception:
            out[n] = "not-importable"
    return out


def probe(app: FastAPI) -> dict[str, Any]:
    """Startup wiring introspection and import/middleware visibility probe.

    This function provides comprehensive diagnostic information about the
    FastAPI application state after startup, including runtime configuration,
    middleware stack, routes, and dependency versions. Used for debugging
    startup performance and configuration issues.
    """
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "current_working_directory": str(Path.cwd()),
        "env_snapshot": _get_env_snapshot(),
        "package_versions": _get_package_versions(),
        "routes": _get_routes_info(app),
        "middlewares": _get_middleware_info(app),
        "lifespan_present": app.router.lifespan_context is not None,
        "elapsed_ms": time.time() * 1000,  # Current timestamp in ms
    }
