from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MemoryClaim:
    claim: str
    evidence: List[str]
    confidence: float  # 0..1
    horizons: List[str]  # ["short", "medium", "long"]
    meta: Dict[str, object] | None = None


__all__ = ["MemoryClaim"]


