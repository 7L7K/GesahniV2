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
from collections.abc import Iterable, Mapping
from typing import Any


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


def _env_list(name: str) -> list[str] | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    # Support comma-separated or \n-separated tokens
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    return [p for p in parts if p]


def base_defaults() -> dict[str, Any]:
    """Return project-wide default generation parameters from env.

    GEN_TEMPERATURE, GEN_TOP_P, GEN_MAX_TOKENS, GEN_STOP
    """

    # For OpenAI, some newer models no longer accept 'max_tokens'.
    # Omit by default unless explicitly set via GEN_MAX_TOKENS.
    max_tokens_env = os.getenv("GEN_MAX_TOKENS", "").strip()
    max_tokens_val = int(max_tokens_env) if max_tokens_env else None
    # Allow env to specify modern param name directly
    max_completion_env = os.getenv("GEN_MAX_COMPLETION_TOKENS", "").strip()
    max_completion_val = int(max_completion_env) if max_completion_env else None
    return {
        # Slightly lower temperature and top_p favour faster, more deterministic
        # generations which benefits low-latency voice pipelines.
        "temperature": _env_float("GEN_TEMPERATURE", 0.1),
        "top_p": _env_float("GEN_TOP_P", 0.9),
        # Default to None; caller/env can opt-in to set an explicit cap
        "max_tokens": max_tokens_val,
        "stop": _env_list("GEN_STOP"),
        "max_completion_tokens": max_completion_val,
    }


def merge_params(overrides: Mapping[str, Any] | None) -> dict[str, Any]:
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


def for_openai(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Map merged params to OpenAI Chat Completions arguments.

    Only includes parameters supported by the Chat Completions API.
    """

    mp = merge_params(overrides)
    out: dict[str, Any] = {
        "temperature": mp.get("temperature"),
        "top_p": mp.get("top_p"),
    }
    # Prefer the newer OpenAI parameter name. If callers provide the legacy
    # 'max_tokens' (via env or overrides), map it to 'max_completion_tokens'.
    # Never include 'max_tokens' in OpenAI requests to avoid 400 errors on
    # newer models.
    if mp.get("max_completion_tokens") is not None:
        out["max_completion_tokens"] = mp.get("max_completion_tokens")
    elif mp.get("max_tokens") is not None:
        out["max_completion_tokens"] = mp.get("max_tokens")
    if mp.get("stop"):
        out["stop"] = mp["stop"]
    # Drop unknown keys to avoid TypeError in SDK
    return {k: v for k, v in out.items() if v is not None}


def for_ollama(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Map merged params to Ollama 'options' payload.

    - temperature -> temperature
    - top_p -> top_p
    - max_tokens -> num_predict
    - stop -> stop (list[str])
    """

    mp = merge_params(overrides)
    out: dict[str, Any] = {
        "temperature": mp.get("temperature"),
        "top_p": mp.get("top_p"),
        "num_predict": mp.get("max_tokens"),
    }
    if mp.get("stop"):
        out["stop"] = mp["stop"]
    # Allow caller to pass additional Ollama-specific options
    extras = {
        k: v
        for k, v in mp.items()
        if k not in {"temperature", "top_p", "max_tokens", "stop"}
    }
    out.update(extras)
    # Remove None values for clean payloads
    return {k: v for k, v in out.items() if v is not None}


__all__ = [
    "base_defaults",
    "merge_params",
    "for_openai",
    "for_ollama",
]
