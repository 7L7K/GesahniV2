from __future__ import annotations

"""Shared GPT model configuration."""


import os

# Default OpenAI model names for various tiers. These can be overridden via env vars.
GPT_BASELINE_MODEL = os.getenv("GPT_BASELINE_MODEL", "gpt-4o-mini")
"""Lightweight, low-cost model suitable for most requests."""

GPT_MID_MODEL = os.getenv("GPT_MID_MODEL", "gpt-4o")
"""Mid-tier model balancing quality and cost."""

GPT_HEAVY_MODEL = os.getenv("GPT_HEAVY_MODEL", "gpt-4o")
"""Heavyweight model for complex or high-accuracy tasks.

Default aligns with tests and routing logic. Override via env if needed.
"""

__all__ = ["GPT_BASELINE_MODEL", "GPT_MID_MODEL", "GPT_HEAVY_MODEL"]
