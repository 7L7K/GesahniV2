from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STORAGE_DIR = Path(__file__).resolve().parents[1] / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

LEDGER_DB = STORAGE_DIR / "ledger.sqlite"
NOTES_DB = STORAGE_DIR / "notes.sqlite"
REMINDERS_DB = STORAGE_DIR / "reminders.sqlite"
SUMMARIES_DB = STORAGE_DIR / "summaries.sqlite"
ALIASES_JSON = STORAGE_DIR / "aliases.json"

# Optional JSONL debug export (kept for debugging; SQLite is authoritative)
LEDGER_FILE = Path(os.getenv("LEDGER_FILE", Path(__file__).resolve().parents[1] / "data" / "ledger.jsonl"))

# Retention defaults
RETENTION_LEDGER_SECONDS = int(48 * 3600)
RETENTION_TRANSCRIPTS_DAYS = 30
RETENTION_SUMMARIES_DAYS = 365

# Deduplication window (seconds)
DEDUPE_WINDOW = int(os.getenv("LEDGER_DEDUPE_WINDOW_S", "10"))


def _conn(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    c.row_factory = sqlite3.Row
    # Use WAL for better durability/concurrency when possible
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    return c


def init_storage() -> None:
    """Create DB files and tables if they do not exist. Add missing columns when upgrading."""
    # Ledger
    with _conn(LEDGER_DB) as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                skill TEXT,
                slots_json TEXT,
                reversible INTEGER,
                reverse_id INTEGER,
                ts TEXT,
                idempotency_key TEXT,
                user_id TEXT
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS ledger_ts_idx ON ledger(ts)")
        c.execute("CREATE INDEX IF NOT EXISTS ledger_idemp_idx ON ledger(idempotency_key)")
        c.execute("CREATE INDEX IF NOT EXISTS ledger_user_idx ON ledger(user_id)")

    # Notes
    with _conn(NOTES_DB) as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                created_at TEXT,
                tags TEXT,
                pinned INTEGER DEFAULT 0
            )
            """
        )

    # Reminders
    with _conn(REMINDERS_DB) as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                when_txt TEXT,
                recurrence TEXT,
                status TEXT,
                created_by TEXT,
                created_at TEXT
            )
            """
        )

    # Summaries
    with _conn(SUMMARIES_DB) as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_txt TEXT UNIQUE,
                bullets_json TEXT,
                source_hash TEXT,
                created_at TEXT
            )
            """
        )

    # Aliases file
    if not ALIASES_JSON.exists():
        ALIASES_JSON.write_text(json.dumps({}, ensure_ascii=False))


def _ensure_ledger_schema() -> None:
    """Add missing columns on upgrade for older DBs (best-effort)."""
    with _conn(LEDGER_DB) as c:
        try:
            cols = [r[1] for r in c.execute("PRAGMA table_info(ledger)").fetchall()]
            if "user_id" not in cols:
                c.execute("ALTER TABLE ledger ADD COLUMN user_id TEXT")
        except Exception:
            pass


def _append_debug_jsonl(record: Dict[str, Any]) -> None:
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
    slots: Optional[Dict[str, Any]] = None,
    reversible: bool = True,
    reverse_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Tuple[bool, int]:
    """Record an action atomically in the SQLite ledger.

    Returns (inserted, rowid). If the entry was deduped by idempotency window,
    inserted will be False and rowid points to the existing entry.
    """
    init_storage()
    _ensure_ledger_schema()
    slots_json = json.dumps(slots or {}, ensure_ascii=False)
    ts = datetime.now(timezone.utc).isoformat()

    with _conn(LEDGER_DB) as c:
        # Deduplicate by idempotency_key within DEDUPE_WINDOW seconds
        if idempotency_key:
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=DEDUPE_WINDOW)).isoformat()
            cur = c.execute(
                "SELECT id, ts FROM ledger WHERE idempotency_key = ? AND ts >= ? ORDER BY ts DESC LIMIT 1",
                (idempotency_key, cutoff),
            )
            row = cur.fetchone()
            if row:
                return False, int(row["id"])

        cur = c.execute(
            "INSERT INTO ledger (type, skill, slots_json, reversible, reverse_id, ts, idempotency_key, user_id) VALUES (?,?,?,?,?,?,?,?)",
            (type, skill, slots_json, 1 if reversible else 0, reverse_id, ts, idempotency_key, user_id),
        )
        rowid = cur.lastrowid

        # Do NOT write JSONL here. JSONL is export-only and must be generated
        # from SQLite on demand to avoid dual-write drift.
        return True, int(rowid)


def export_ledger_jsonl(target_path: Path) -> None:
    """Export the entire ledger table to a newline-delimited JSON file.

    This is an export-only helper; production writes must go to SQLite only.
    """
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with _conn(LEDGER_DB) as c:
            rows = c.execute("SELECT * FROM ledger ORDER BY ts ASC").fetchall()
            with open(target_path, "w", encoding="utf-8") as f:
                for r in rows:
                    try:
                        f.write(json.dumps({k: r[k] for k in r.keys()}, ensure_ascii=False) + "\n")
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
        with _conn(LEDGER_DB) as c:
            c.execute("UPDATE ledger SET reverse_id = ? WHERE id = ?", (reverse_id, forward_id))
    except Exception:
        pass


def add_note(text: str, tags: Optional[List[str]] = None, pinned: bool = False) -> int:
    init_storage()
    tags_txt = json.dumps(tags or [], ensure_ascii=False)
    created_at = datetime.now(timezone.utc).isoformat()
    with _conn(NOTES_DB) as c:
        cur = c.execute("INSERT INTO notes (text, created_at, tags, pinned) VALUES (?,?,?,?)", (text, created_at, tags_txt, 1 if pinned else 0))
        return cur.lastrowid


def add_reminder(text: str, when_txt: str, recurrence: Optional[str] = None, created_by: Optional[str] = None) -> int:
    init_storage()
    created_at = datetime.now(timezone.utc).isoformat()
    with _conn(REMINDERS_DB) as c:
        cur = c.execute(
            "INSERT INTO reminders (text, when_txt, recurrence, status, created_by, created_at) VALUES (?,?,?,?,?,?)",
            (text, when_txt, recurrence or "", "pending", created_by, created_at),
        )
        return cur.lastrowid


def save_alias(alias: str, entity_id: str, confidence: float = 1.0) -> None:
    init_storage()
    try:
        data = json.loads(ALIASES_JSON.read_text(encoding="utf-8") or "{}")
    except Exception:
        data = {}
    data[alias] = {"entity": entity_id, "confidence": float(confidence), "last_used": datetime.now(timezone.utc).isoformat()}
    ALIASES_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_aliases() -> Dict[str, Dict[str, Any]]:
    init_storage()
    try:
        return json.loads(ALIASES_JSON.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def save_summary(date_txt: str, bullets: List[str], source_hash: Optional[str] = None) -> int:
    init_storage()
    created_at = datetime.now(timezone.utc).isoformat()
    bullets_json = json.dumps(bullets, ensure_ascii=False)
    with _conn(SUMMARIES_DB) as c:
        cur = c.execute(
            "INSERT OR REPLACE INTO summaries (date_txt, bullets_json, source_hash, created_at) VALUES (?,?,?,?)",
            (date_txt, bullets_json, source_hash or "", created_at),
        )
        return cur.lastrowid


def get_last_reversible_action(user_id: Optional[str] = None, action_types: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    init_storage()
    _ensure_ledger_schema()
    q = "SELECT * FROM ledger WHERE reversible = 1"
    params: List[Any] = []
    if user_id:
        q += " AND user_id = ?"
        params.append(user_id)
    if action_types:
        placeholders = ",".join(["?" for _ in action_types])
        q += f" AND type IN ({placeholders})"
        params.extend(action_types)
    q += " ORDER BY ts DESC LIMIT 1"

    with _conn(LEDGER_DB) as c:
        cur = c.execute(q, params)
        row = cur.fetchone()
        if not row:
            return None
        try:
            slots = json.loads(row["slots_json"] or "{}")
        except Exception:
            slots = {}
        return {
            "id": int(row["id"]),
            "type": row["type"],
            "skill": row["skill"],
            "slots": slots,
            "reversible": bool(row["reversible"]),
            "reverse_id": row["reverse_id"],
            "ts": row["ts"],
            "idempotency_key": row["idempotency_key"],
            "user_id": row["user_id"],
        }


def prune_retention() -> None:
    """Prune according to retention policies (best-effort, synchronous)."""
    init_storage()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=RETENTION_LEDGER_SECONDS)).isoformat()
    with _conn(LEDGER_DB) as c:
        c.execute("DELETE FROM ledger WHERE ts < ?", (cutoff,))


