"""Helpers for interpreting environment variables consistently."""

from __future__ import annotations

import os
from typing import Iterable

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def env_flag(
    name: str,
    *,
    default: bool = False,
    legacy: Iterable[str] | None = None,
) -> bool:
    """Return a boolean flag from the environment.

    Parameters are evaluated in order, supporting optional legacy names for
    staged migrations. Values default to ``default`` when unset or empty.
    """

    candidates = (name, *tuple(legacy or ()))
    for key in candidates:
        raw = os.getenv(key)
        if raw is None:
            continue
        value = raw.strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in _TRUTHY:
            return True
        if lowered in _FALSY:
            return False
    return bool(default)


def require_env(name: str) -> str:
    """Return the value for ``name`` or raise if missing."""

    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"{name} missing")
