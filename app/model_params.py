"""Unified generation parameter handling for GPT and LLaMA backends.

Provides a single place to define defaults (via env) and to translate
parameters into each provider's specific option names.

Supported params (common):
- temperature: float
- top_p: float
- max_tokens: int
- stop: list[str] | str | None
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Mapping


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_list(name: str) -> List[str] | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    # Support comma-separated or \n-separated tokens
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    return [p for p in parts if p]


def base_defaults() -> Dict[str, Any]:
    """Return project-wide default generation parameters from env.

    GEN_TEMPERATURE, GEN_TOP_P, GEN_MAX_TOKENS, GEN_STOP
    """

    return {
        "temperature": _env_float("GEN_TEMPERATURE", 0.2),
        "top_p": _env_float("GEN_TOP_P", 0.95),
        "max_tokens": _env_int("GEN_MAX_TOKENS", 512),
        "stop": _env_list("GEN_STOP"),
    }


def merge_params(overrides: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Return defaults merged with optional overrides (None values ignored)."""

    base = base_defaults()
    if not overrides:
        return base
    for k, v in overrides.items():
        if v is None:
            continue
        if k == "stop":
            # Normalize stop to list[str]
            if isinstance(v, str):
                base["stop"] = [v]
            elif isinstance(v, Iterable):
                base["stop"] = [str(x) for x in v if str(x)]
            else:
                # ignore invalid types
                pass
        elif k in {"temperature", "top_p", "max_tokens"}:
            base[k] = v
        else:
            # allow additional provider-specific keys to flow through unchanged
            base[k] = v
    return base


def for_openai(overrides: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Map merged params to OpenAI Chat Completions arguments.

    Only includes parameters supported by the Chat Completions API.
    """

    mp = merge_params(overrides)
    out: Dict[str, Any] = {
        "temperature": mp.get("temperature"),
        "top_p": mp.get("top_p"),
        "max_tokens": mp.get("max_tokens"),
    }
    if mp.get("stop"):
        out["stop"] = mp["stop"]
    # Drop unknown keys to avoid TypeError in SDK
    return {k: v for k, v in out.items() if v is not None}


def for_ollama(overrides: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Map merged params to Ollama 'options' payload.

    - temperature -> temperature
    - top_p -> top_p
    - max_tokens -> num_predict
    - stop -> stop (list[str])
    """

    mp = merge_params(overrides)
    out: Dict[str, Any] = {
        "temperature": mp.get("temperature"),
        "top_p": mp.get("top_p"),
        "num_predict": mp.get("max_tokens"),
    }
    if mp.get("stop"):
        out["stop"] = mp["stop"]
    # Allow caller to pass additional Ollama-specific options
    extras = {k: v for k, v in mp.items() if k not in {"temperature", "top_p", "max_tokens", "stop"}}
    out.update(extras)
    # Remove None values for clean payloads
    return {k: v for k, v in out.items() if v is not None}


__all__ = [
    "base_defaults",
    "merge_params",
    "for_openai",
    "for_ollama",
]


