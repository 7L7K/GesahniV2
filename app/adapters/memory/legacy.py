from __future__ import annotations

from app.memory import api as _api
from app.redaction import redact_pii, store_redaction_map

from ._types import MemoryBackend


class LegacyMemoryBackend(MemoryBackend):
    """Adapter around the existing vector-store API."""

    def add(
        self,
        user_id: str,
        text: str,
        *,
        tags: list[str] | None = None,
        meta: dict | None = None,
    ) -> str:
        try:
            redacted, mapping = redact_pii(text)
            mem_id = _api.add_user_memory(user_id, redacted)
            try:
                store_redaction_map("user_memory", mem_id, mapping)
            except Exception:
                pass
            return mem_id
        except Exception:
            return _api.add_user_memory(user_id, text)

    def search(
        self,
        user_id: str,
        query: str,
        *,
        k: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        # ``query_user_memories`` returns raw strings; wrap in dicts for adapter
        res = _api.query_user_memories(user_id, query, k)
        return [{"text": r} for r in res]

    def upsert_entity(self, kind: str, name: str, **attrs) -> str:  # pragma: no cover - noop
        # Legacy vector store has no entity graph; return synthesized id
        return f"{kind}:{name}"

    def link(self, src_id: str, rel: str, dst_id: str, **attrs) -> None:  # pragma: no cover - noop
        # Relationship creation is a no-op for the legacy backend
        return None
