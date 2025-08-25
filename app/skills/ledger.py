from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app import storage


async def record_action(
    action_type: str,
    idempotency_key: Optional[str],
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    reversible: bool = True,
) -> bool:
    """Record an action using the centralized SQLite ledger.

    Returns True when a new entry was recorded, False when deduped.
    The storage layer is authoritative; this function adapts the legacy call
    shape to the storage API and preserves the optional JSONL debug export.
    """
    metadata = metadata or {}
    # Expect callers to pass `skill` and `slots` inside metadata when relevant.
    skill = metadata.get("skill", metadata.get("source", "unknown"))
    slots = metadata.get("slots", {k: v for k, v in metadata.items() if k != "skill"})

    inserted, rowid = storage.record_ledger(
        type=action_type,
        skill=skill,
        slots=slots,
        reversible=reversible,
        reverse_id=metadata.get("reverse_id"),
        idempotency_key=idempotency_key,
        user_id=user_id,
    )
    # Convert storage-layer rowid into usable reverse_id linkage: the storage
    # API returns (inserted, rowid). We return True/False for backwards
    # compatibility, but callers that need the rowid should use storage.record_ledger
    return bool(inserted)


async def get_last_reversible_action(user_id: Optional[str] = None, action_types: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Query the authoritative SQLite ledger for the latest reversible action.

    Returns a dict with keys: id, type, skill, slots, reversible, reverse_id, ts, idempotency_key, user_id
    """
    return storage.get_last_reversible_action(user_id=user_id, action_types=action_types)

