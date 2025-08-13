from __future__ import annotations

import json
import os
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite


def _compute_db_path() -> Path:
    env_path = os.getenv("CARE_DB")
    if env_path:
        return Path(env_path).resolve()
    if os.getenv("PYTEST_CURRENT_TEST"):
        ident = os.getenv("PYTEST_CURRENT_TEST", "")
        digest = hashlib.md5(ident.encode()).hexdigest()[:8]
        p = Path.cwd() / f".tmp_care_{digest}.db"
    else:
        p = Path("care.db")
    return p.resolve()


DB_PATH = _compute_db_path()
try:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


def _now() -> float:
    return time.time()


async def ensure_tables() -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS residents (
                id TEXT PRIMARY KEY,
                name TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS caregivers (
                id TEXT PRIMARY KEY,
                name TEXT,
                phone TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS caregiver_resident (
                caregiver_id TEXT,
                resident_id TEXT,
                primary_flag INTEGER DEFAULT 0,
                UNIQUE(caregiver_id, resident_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                resident_id TEXT,
                last_seen REAL,
                battery_pct INTEGER,
                battery_low_since REAL,
                battery_notified INTEGER DEFAULT 0,
                offline_since REAL,
                offline_notified INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                resident_id TEXT,
                kind TEXT,
                severity TEXT,
                note TEXT,
                created_at REAL,
                status TEXT,
                ack_at REAL,
                resolved_at REAL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT,
                t REAL,
                type TEXT,
                meta TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS care_sessions (
                id TEXT PRIMARY KEY,
                resident_id TEXT,
                title TEXT,
                transcript_uri TEXT,
                created_at REAL,
                updated_at REAL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                resident_id TEXT,
                name TEXT,
                phone TEXT,
                priority INTEGER,
                quiet_hours TEXT
            )
            """
        )
        await db.commit()


async def insert_alert(rec: Dict[str, Any]) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            INSERT INTO alerts (id, resident_id, kind, severity, note, created_at, status, ack_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec["id"],
                rec["resident_id"],
                rec["kind"],
                rec["severity"],
                rec.get("note", ""),
                rec.get("created_at", _now()),
                rec.get("status", "open"),
                rec.get("ack_at"),
                rec.get("resolved_at"),
            ),
        )
        await db.commit()


async def get_alert(alert_id: str) -> Optional[Dict[str, Any]]:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(
            "SELECT id,resident_id,kind,severity,note,created_at,status,ack_at,resolved_at FROM alerts WHERE id=?",
            (alert_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    keys = [
        "id",
        "resident_id",
        "kind",
        "severity",
        "note",
        "created_at",
        "status",
        "ack_at",
        "resolved_at",
    ]
    return {k: row[i] for i, k in enumerate(keys)}


async def update_alert(alert_id: str, **fields: Any) -> None:
    await ensure_tables()
    if not fields:
        return
    cols = ",".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [alert_id]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(f"UPDATE alerts SET {cols} WHERE id=?", vals)
        await db.commit()


async def insert_event(alert_id: str, type_: str, meta: Dict[str, Any] | None = None) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO alert_events (alert_id, t, type, meta) VALUES (?, ?, ?, ?)",
            (alert_id, _now(), type_, json.dumps(meta or {})),
        )
        await db.commit()


async def list_alerts(resident_id: Optional[str] = None) -> List[Dict[str, Any]]:
    await ensure_tables()
    q = "SELECT id,resident_id,kind,severity,note,created_at,status,ack_at,resolved_at FROM alerts"
    params: tuple = ()
    if resident_id:
        q += " WHERE resident_id=?"
        params = (resident_id,)
    q += " ORDER BY created_at DESC"
    out: List[Dict[str, Any]] = []
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(q, params) as cur:
            async for row in cur:
                out.append(
                    {
                        "id": row[0],
                        "resident_id": row[1],
                        "kind": row[2],
                        "severity": row[3],
                        "note": row[4],
                        "created_at": row[5],
                        "status": row[6],
                        "ack_at": row[7],
                        "resolved_at": row[8],
                    }
                )
    return out


async def upsert_device(device_id: str, resident_id: str, *, battery_pct: Optional[int] = None) -> Dict[str, Any]:
    await ensure_tables()
    now = _now()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        # Fetch current
        async with db.execute(
            "SELECT id,resident_id,last_seen,battery_pct,battery_low_since,battery_notified,offline_since,offline_notified FROM devices WHERE id=?",
            (device_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            battery_low_since = None
            offline_since = None
            await db.execute(
                "INSERT INTO devices (id,resident_id,last_seen,battery_pct,battery_low_since,offline_since) VALUES (?,?,?,?,?,?)",
                (device_id, resident_id, now, battery_pct, battery_low_since, offline_since),
            )
            await db.commit()
            return {
                "id": device_id,
                "resident_id": resident_id,
                "last_seen": now,
                "battery_pct": battery_pct,
                "battery_low_since": battery_low_since,
                "battery_notified": 0,
                "offline_since": offline_since,
                "offline_notified": 0,
            }
        # Update
        last_seen = now
        current_batt = row[3]
        batt = battery_pct if battery_pct is not None else current_batt
        batt_low_since = row[4]
        batt_notified = row[5]
        off_since = row[6]
        off_notified = row[7]
        if batt is not None and batt < 15:
            batt_low_since = batt_low_since or now
        else:
            batt_low_since = None
            batt_notified = 0
        # offline tracking handled by caller using status computation
        await db.execute(
            "UPDATE devices SET resident_id=?, last_seen=?, battery_pct=?, battery_low_since=?, battery_notified=?, offline_since=?, offline_notified=? WHERE id=?",
            (resident_id, last_seen, batt, batt_low_since, batt_notified, off_since, off_notified, device_id),
        )
        await db.commit()
        return {
            "id": device_id,
            "resident_id": resident_id,
            "last_seen": last_seen,
            "battery_pct": batt,
            "battery_low_since": batt_low_since,
            "battery_notified": batt_notified,
            "offline_since": off_since,
            "offline_notified": off_notified,
        }


async def get_device(device_id: str) -> Optional[Dict[str, Any]]:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(
            "SELECT id,resident_id,last_seen,battery_pct,battery_low_since,battery_notified,offline_since,offline_notified FROM devices WHERE id=?",
            (device_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        # Ensure initial query returns a consistent offline stub
        return {
            "id": device_id,
            "resident_id": None,
            "last_seen": 0.0,
            "battery_pct": None,
            "battery_low_since": None,
            "battery_notified": 0,
            "offline_since": None,
            "offline_notified": 0,
        }
    return {
        "id": row[0],
        "resident_id": row[1],
        "last_seen": row[2],
        "battery_pct": row[3],
        "battery_low_since": row[4],
        "battery_notified": row[5],
        "offline_since": row[6],
        "offline_notified": row[7],
    }


async def set_device_flags(device_id: str, **flags: Any) -> None:
    await ensure_tables()
    if not flags:
        return
    cols = ",".join(f"{k}=?" for k in flags)
    vals = list(flags.values()) + [device_id]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(f"UPDATE devices SET {cols} WHERE id=?", vals)
        await db.commit()


async def list_devices() -> List[Dict[str, Any]]:
    await ensure_tables()
    out: List[Dict[str, Any]] = []
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(
            "SELECT id,resident_id,last_seen,battery_pct,battery_low_since,battery_notified,offline_since,offline_notified FROM devices"
        ) as cur:
            async for row in cur:
                out.append(
                    {
                        "id": row[0],
                        "resident_id": row[1],
                        "last_seen": row[2],
                        "battery_pct": row[3],
                        "battery_low_since": row[4],
                        "battery_notified": row[5],
                        "offline_since": row[6],
                        "offline_notified": row[7],
                    }
                )
    return out


# Sessions --------------------------------------------------------------------

async def create_session(rec: Dict[str, Any]) -> None:
    await ensure_tables()
    now = _now()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO care_sessions (id,resident_id,title,transcript_uri,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (
                rec["id"],
                rec["resident_id"],
                rec.get("title", ""),
                rec.get("transcript_uri"),
                now,
                now,
            ),
        )
        await db.commit()


async def update_session(session_id: str, **fields: Any) -> None:
    await ensure_tables()
    if not fields:
        return
    fields["updated_at"] = _now()
    cols = ",".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [session_id]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(f"UPDATE care_sessions SET {cols} WHERE id=?", vals)
        await db.commit()


async def list_sessions(resident_id: Optional[str] = None) -> List[Dict[str, Any]]:
    await ensure_tables()
    q = "SELECT id,resident_id,title,transcript_uri,created_at,updated_at FROM care_sessions"
    params: tuple = ()
    if resident_id:
        q += " WHERE resident_id=?"
        params = (resident_id,)
    q += " ORDER BY created_at DESC"
    out: List[Dict[str, Any]] = []
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(q, params) as cur:
            async for row in cur:
                out.append(
                    {
                        "id": row[0],
                        "resident_id": row[1],
                        "title": row[2],
                        "transcript_uri": row[3],
                        "created_at": row[4],
                        "updated_at": row[5],
                    }
                )
    return out


async def create_contact(rec: Dict[str, Any]) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO contacts (id,resident_id,name,phone,priority,quiet_hours) VALUES (?,?,?,?,?,?)",
            (rec["id"], rec["resident_id"], rec["name"], rec.get("phone"), int(rec.get("priority", 0)), json.dumps(rec.get("quiet_hours") or {})),
        )
        await db.commit()


async def list_contacts(resident_id: str) -> List[Dict[str, Any]]:
    await ensure_tables()
    out: List[Dict[str, Any]] = []
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(
            "SELECT id,resident_id,name,phone,priority,quiet_hours FROM contacts WHERE resident_id=? ORDER BY priority DESC",
            (resident_id,),
        ) as cur:
            async for row in cur:
                out.append(
                    {
                        "id": row[0],
                        "resident_id": row[1],
                        "name": row[2],
                        "phone": row[3],
                        "priority": row[4],
                        "quiet_hours": json.loads(row[5] or "{}"),
                    }
                )
    return out


async def update_contact(contact_id: str, **fields: Any) -> None:
    await ensure_tables()
    if not fields:
        return
    if "quiet_hours" in fields and isinstance(fields["quiet_hours"], (dict, list)):
        fields["quiet_hours"] = json.dumps(fields["quiet_hours"])
    cols = ",".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [contact_id]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(f"UPDATE contacts SET {cols} WHERE id=?", vals)
        await db.commit()


async def delete_contact(contact_id: str) -> None:
    await ensure_tables()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
        await db.commit()


