from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Flag:
    key: str
    description: str
    default: str
    type: str = "str"  # str|bool|int|float

    @property
    def env_key(self) -> str:
        return f"FLAG_{self.key.upper()}"


_REGISTRY: Dict[str, Flag] = {}
_overrides: Dict[str, str] = {}


def register(key: str, description: str, default: str, type: str = "str") -> None:
    _REGISTRY[key] = Flag(key=key, description=description, default=default, type=type)


def coerce(value: str, ty: str) -> Any:
    if ty == "bool":
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if ty == "int":
        return int(value)
    if ty == "float":
        return float(value)
    return value


def get_value(key: str) -> str:
    if key in _overrides:
        return _overrides[key]
    f = _REGISTRY.get(key)
    if not f:
        # Fallback to raw env for unknown keys to preserve behavior
        return os.getenv(f"FLAG_{key.upper()}", "")
    return os.getenv(f.env_key, f.default)


def get(key: str) -> Any:
    f = _REGISTRY.get(key)
    raw = get_value(key)
    return coerce(raw, f.type if f else "str")


def set_value(key: str, value: str) -> None:
    # In-memory override; admin change is process-local by design
    _overrides[key] = value


def clear_value(key: str) -> None:
    _overrides.pop(key, None)


def list_flags() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    keys = sorted(_REGISTRY.keys())
    for k in keys:
        f = _REGISTRY[k]
        current = get_value(k)
        out[k] = {
            "description": f.description,
            "default": f.default,
            "type": f.type,
            "value": current,
            "env": f.env_key,
            "overridden": k in _overrides,
        }
    return out


# Built-in flags (extend as needed)
register("RETRIEVAL_PIPELINE", "Use structured retrieval pipeline", "1", "bool")
register("CANARY_ENABLE", "Enable canary routing for eligible users", "0", "bool")
register("UI_GRANNY_MODE", "Enable simplified UI mode", "0", "bool")


__all__ = [
    "register",
    "list_flags",
    "get",
    "set_value",
    "clear_value",
]


