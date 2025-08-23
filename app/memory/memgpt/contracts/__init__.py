from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MemoryClaim:
    claim: str
    evidence: list[str]
    confidence: float  # 0..1
    horizons: list[str]  # ["short", "medium", "long"]
    meta: dict[str, object] | None = None


__all__ = ["MemoryClaim"]
