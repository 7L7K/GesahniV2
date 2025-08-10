from __future__ import annotations

from typing import Protocol


class MemoryBackend(Protocol):
    """Abstract memory backend interface."""

    def add(
        self,
        user_id: str,
        text: str,
        *,
        tags: list[str] | None = None,
        meta: dict | None = None,
    ) -> str:
        """Store a memory snippet for ``user_id`` and return its id."""

    def search(
        self,
        user_id: str,
        query: str,
        *,
        k: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        """Return up to ``k`` memory objects matching ``query``."""

    def upsert_entity(self, kind: str, name: str, **attrs) -> str:
        """Create or update an entity node and return its id."""

    def link(self, src_id: str, rel: str, dst_id: str, **attrs) -> None:
        """Create a relationship between two stored ids."""
