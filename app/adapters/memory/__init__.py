from __future__ import annotations

from ._types import MemoryBackend
from .legacy import LegacyMemoryBackend

# In future this module can select between multiple backends (mem0, graphiti, etc.)
mem: MemoryBackend = LegacyMemoryBackend()

__all__ = ["mem", "MemoryBackend"]
