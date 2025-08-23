from __future__ import annotations

import os
from typing import Any, Dict, Tuple


def is_enabled(flag: str, *, default: bool = False) -> bool:
    val = os.getenv(f"FLAG_{flag.upper()}", "1" if default else "0").lower()
    return val in {"1", "true", "yes"}


_WINS: dict[str, int] = {}
_LOSSES: dict[str, int] = {}


def record_result(flag: str, win: bool) -> None:
    ( _WINS if win else _LOSSES )[flag] = ( _WINS if win else _LOSSES ).get(flag, 0) + 1


def snapshot() -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    keys = set(_WINS) | set(_LOSSES)
    for k in keys:
        out[k] = (_WINS.get(k, 0), _LOSSES.get(k, 0))
    return out


__all__ = ["is_enabled", "record_result", "snapshot"]


