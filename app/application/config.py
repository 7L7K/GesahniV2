from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from app.config_docs import get_docs_visibility_config, get_swagger_ui_parameters

logger = logging.getLogger(__name__)

TAGS_METADATA: list[Mapping[str, str]] = [
    {
        "name": "Care",
        "description": "Care features, contacts, sessions, and Home Assistant actions.",
    },
    {"name": "Music", "description": "Music playback, voices, and TTS."},
    {"name": "Calendar", "description": "Calendar and reminders."},
    {"name": "TV", "description": "TV UI and related endpoints."},
    {"name": "Admin", "description": "Admin, status, models, diagnostics, and tools."},
    {"name": "Auth", "description": "Authentication and authorization."},
]


def derive_version() -> str:
    """Return a semantic version string for the API."""
    env_version = os.getenv("APP_VERSION") or os.getenv("GIT_TAG")
    if env_version:
        return env_version

    try:
        proc = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (proc.stdout or "").strip()
        if output:
            return output
    except Exception as exc:  # pragma: no cover - git might be unavailable
        logger.debug("Failed to derive version from git: %s", exc)

    return "0.0.0"


@lru_cache
def load_openapi_config() -> dict[str, Any]:
    """Return documentation visibility and Swagger configuration."""
    config = get_docs_visibility_config().copy()
    config["swagger_ui_parameters"] = get_swagger_ui_parameters()
    config["dev_servers_snapshot"] = os.getenv("OPENAPI_DEV_SERVERS")
    return config


__all__ = ["TAGS_METADATA", "derive_version", "load_openapi_config"]
