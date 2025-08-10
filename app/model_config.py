"""Shared GPT model configuration."""

from __future__ import annotations

import os

# Default OpenAI model names for various tiers. These can be overridden via env vars.
GPT_BASELINE_MODEL = os.getenv("GPT_BASELINE_MODEL", "gpt-4o-mini")
"""Lightweight, low-cost model suitable for most requests."""

GPT_MID_MODEL = os.getenv("GPT_MID_MODEL", "gpt-4o")
"""Mid-tier model balancing quality and cost."""

GPT_HEAVY_MODEL = os.getenv("GPT_HEAVY_MODEL", "o4-mini")
"""Heavyweight model for complex or high-accuracy tasks."""

__all__ = ["GPT_BASELINE_MODEL", "GPT_MID_MODEL", "GPT_HEAVY_MODEL"]
