from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB as JSON

from .db.core import sync_engine
from .util.ids import to_uuid

STORAGE_DIR = Path(__file__).resolve().parents[1] / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

ALIASES_JSON = STORAGE_DIR / "aliases.json"

# Optional JSONL debug export (kept for debugging; PostgreSQL is authoritative)
LEDGER_FILE = Path(
    os.getenv(
        "LEDGER_FILE", Path(__file__).resolve().parents[1] / "data" / "ledger.jsonl"
    )
)

# Retention defaults
RETENTION_LEDGER_SECONDS = int(48 * 3600)
RETENTION_TRANSCRIPTS_DAYS = 30
RETENTION_SUMMARIES_DAYS = 365

# Deduplication window (seconds)
DEDUPE_WINDOW = int(os.getenv("LEDGER_DEDUPE_WINDOW_S", "10"))


def _pg_exec(query: str | text, params: dict[str, Any] | None = None) -> None:
    with sync_engine.begin() as conn:
        if isinstance(query, str):
            conn.execute(text(query), params or {})
        else:
            # query is already a TextClause with bound params
            conn.execute(query, params or {})


def _pg_fetchone(query: str | text, params: dict[str, Any]) -> dict[str, Any] | None:
    with sync_engine.connect() as conn:
        if isinstance(query, str):
            res = conn.execute(text(query), params)
        else:
            # query is already a TextClause with bound params
            res = conn.execute(query, params)
        row = res.mappings().first()
        return dict(row) if row else None


def init_storage() -> None:
    """No-op for PostgreSQL-managed schemas (migrations create objects)."""

    # Aliases file
    if not ALIASES_JSON.exists():
        ALIASES_JSON.write_text(json.dumps({}, ensure_ascii=False))


def _ensure_ledger_schema() -> None:
    return None


def _append_debug_jsonl(record: dict[str, Any]) -> None:
    """Append to optional JSONL debug file; best-effort."""
    try:
        LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def record_ledger(
    type: str,
    skill: str,
    slots: dict[str, Any] | None = None,
    reversible: bool = True,
    reverse_id: int | None = None,
    idempotency_key: str | None = None,
    user_id: str | None = None,
) -> tuple[bool, int]:
    """Record an action atomically in PostgreSQL storage.ledger.

    Returns (inserted, rowid). If unique conflict on (user_id, idempotency_key),
    inserted will be False and rowid points to the existing entry.
    """
    init_storage()
    meta: dict[str, Any] = {
        "skill": skill,
        "slots": slots or {},
        "reversible": bool(reversible),
        "reverse_id": reverse_id,
        "type": type,
    }
    now = datetime.now(UTC)
    # Attempt insert with ON CONFLICT DO NOTHING
    stmt = text(
        """
        INSERT INTO storage.ledger (user_id, idempotency_key, operation, amount, metadata, created_at)
        VALUES (:user_id, :idempotency_key, :operation, NULL, :metadata, :created_at)
        ON CONFLICT (user_id, idempotency_key) DO NOTHING
        """
    ).bindparams(
        bindparam("user_id"),
        bindparam("idempotency_key"),
        bindparam("operation"),
        bindparam("metadata", type_=JSON),
        bindparam("created_at"),
    )
    _pg_exec(
        stmt,
        {
            "user_id": str(to_uuid(user_id)) if user_id else user_id,
            "idempotency_key": idempotency_key,
            "operation": type,
            "metadata": meta,  # Pass the dict directly, not json.dumps()
            "created_at": now,
        },
    )
    # Fetch id
    row = _pg_fetchone(
        "SELECT id FROM storage.ledger WHERE user_id = :user_id AND idempotency_key = :idempotency_key",
        {
            "user_id": str(to_uuid(user_id)) if user_id else user_id,
            "idempotency_key": idempotency_key,
        },
    )
    inserted = True
    if row is None:
        # Rare: idempotency_key None or not provided -> best-effort insert then fetch
        row = _pg_fetchone(
            "SELECT id FROM storage.ledger WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 1",
            {"user_id": str(to_uuid(user_id)) if user_id else ""},
        )
    else:
        # If the row existed, then not inserted
        inserted = False
    return bool(inserted), int(row["id"]) if row and "id" in row else 0


def export_ledger_jsonl(target_path: Path) -> None:
    """Export the entire ledger table to a newline-delimited JSON file.

    This is an export-only helper; production writes must go to PostgreSQL only.
    """
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with sync_engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT id, user_id, idempotency_key, operation, amount, metadata, created_at FROM storage.ledger ORDER BY created_at ASC"
                    )
                )
                .mappings()
                .all()
            )
            with open(target_path, "w", encoding="utf-8") as f:
                for r in rows:
                    try:
                        f.write(json.dumps(dict(r), ensure_ascii=False) + "\n")
                    except Exception:
                        continue
    except Exception:
        pass


def link_reverse(forward_id: int, reverse_id: int) -> None:
    """Link a forward ledger entry to its reverse by updating reverse_id.

    Best-effort; used when an undo is recorded so forward.reverse_id points to
    the undo row.
    """
    try:
        stmt = text(
            """
            UPDATE storage.ledger SET metadata = jsonb_set(COALESCE(metadata,'{}'::jsonb), '{reverse_id}', to_jsonb(:reverse_id), true)
            WHERE id = :forward_id
            """
        ).bindparams(
            bindparam("reverse_id", type_=int),
            bindparam("forward_id", type_=int),
        )
        _pg_exec(
            stmt,
            {"reverse_id": reverse_id, "forward_id": forward_id},
        )
    except Exception:
        pass


def add_note(text: str, tags: list[str] | None = None, pinned: bool = False) -> int:
    created_at = datetime.now(UTC)
    row = _pg_fetchone(
        """
        INSERT INTO user_data.notes (user_id, text, created_at)
        VALUES (:user_id, :text, :created_at)
        RETURNING id
        """,
        {
            "user_id": os.getenv(
                "DEFAULT_NOTES_USER_ID", "00000000-0000-0000-0000-000000000001"
            ),
            "text": text,
            "created_at": created_at,
        },
    )
    return int(row["id"]) if row else 0


def add_reminder(
    text: str,
    when_txt: str,
    recurrence: str | None = None,
    created_by: str | None = None,
) -> int:
    # Not yet implemented in PG; placeholder returns 0
    return 0


def save_alias(alias: str, entity_id: str, confidence: float = 1.0) -> None:
    init_storage()
    try:
        data = json.loads(ALIASES_JSON.read_text(encoding="utf-8") or "{}")
    except Exception:
        data = {}
    data[alias] = {
        "entity": entity_id,
        "confidence": float(confidence),
        "last_used": datetime.now(UTC).isoformat(),
    }
    ALIASES_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_aliases() -> dict[str, dict[str, Any]]:
    init_storage()
    try:
        return json.loads(ALIASES_JSON.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def save_summary(
    date_txt: str, bullets: list[str], source_hash: str | None = None
) -> int:
    # Not yet implemented in PG; placeholder returns 0
    return 0


def get_last_reversible_action(
    user_id: str | None = None, action_types: list[str] | None = None
) -> dict[str, Any] | None:
    where = ["(metadata->>'reversible')::boolean = true"]
    params: dict[str, Any] = {}
    if user_id:
        where.append("user_id = :user_id")
        params["user_id"] = str(to_uuid(user_id))
    if action_types:
        where.append("operation = ANY(:ops)")
        params["ops"] = action_types
    q = f"SELECT id, user_id, idempotency_key, operation, metadata, created_at FROM storage.ledger WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT 1"
    row = _pg_fetchone(q, params)
    if not row:
        return None
    md = row.get("metadata") or {}
    try:
        slots = (md or {}).get("slots") or {}
    except Exception:
        slots = {}
    return {
        "id": int(row["id"]),
        "type": row.get("operation"),
        "skill": (md or {}).get("skill"),
        "slots": slots,
        "reversible": True,
        "reverse_id": (md or {}).get("reverse_id"),
        "ts": row.get("created_at").isoformat() if row.get("created_at") else None,
        "idempotency_key": row.get("idempotency_key"),
        "user_id": row.get("user_id"),
    }


def prune_retention() -> None:
    """Prune according to retention policies (best-effort, synchronous)."""
    cutoff = datetime.now(UTC) - timedelta(seconds=RETENTION_LEDGER_SECONDS)
    _pg_exec(
        "DELETE FROM storage.ledger WHERE created_at < :cutoff", {"cutoff": cutoff}
    )
