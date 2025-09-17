from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db.core import sync_engine

# Note: resolve_db_path import removed as it's no longer needed for PostgreSQL


def _compute_db_path() -> Path:
    """Deprecated: Care data now stored in PostgreSQL via app.db.core."""
    # Return a dummy path since we no longer use legacy file-backed store files
    return Path("/dev/null")


def _db_path() -> Path:
    """Deprecated: Care data now stored in PostgreSQL via app.db.core."""
    # Return a dummy path since we no longer use legacy file-backed store files
    return Path("/dev/null")


def _now():
    from datetime import datetime

    return datetime.now(UTC)


async def ensure_tables() -> None:
    """Ensure care-related tables exist in PostgreSQL (created by Phase 2 migrations)."""
    # Tables are now created by Phase 2 migrations, so this is a no-op
    # Kept for API compatibility
    pass


async def insert_alert(rec: dict[str, Any]) -> None:
    """Insert alert into PostgreSQL care.alerts table."""
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO care.alerts (id, resident_id, kind, severity, note, created_at, status, ack_at, resolved_at)
                VALUES (:id, :resident_id, :kind, :severity, :note, :created_at, :status, :ack_at, :resolved_at)
            """
            ),
            {
                "id": rec["id"],
                "resident_id": rec["resident_id"],
                "kind": rec["kind"],
                "severity": rec["severity"],
                "note": rec.get("note", ""),
                "created_at": rec.get("created_at", _now()),
                "status": rec.get("status", "open"),
                "ack_at": rec.get("ack_at"),
                "resolved_at": rec.get("resolved_at"),
            },
        )


async def get_alert(alert_id: str) -> dict[str, Any] | None:
    """Get alert from PostgreSQL care.alerts table."""
    with sync_engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, resident_id, kind, severity, note, created_at, status, ack_at, resolved_at
                FROM care.alerts WHERE id = :alert_id
            """
            ),
            {"alert_id": alert_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None


async def update_alert(alert_id: str, **fields: Any) -> None:
    """Update alert in PostgreSQL care.alerts table."""
    if not fields:
        return
    # Build dynamic UPDATE query with named parameters
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "alert_id": alert_id}

    with sync_engine.begin() as conn:
        conn.execute(
            text(f"UPDATE care.alerts SET {set_clause} WHERE id = :alert_id"), params
        )


async def insert_event(
    alert_id: str, type_: str, meta: dict[str, Any] | None = None
) -> None:
    """Insert event into PostgreSQL care.alert_events table."""
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO care.alert_events (alert_id, t, type, meta)
                VALUES (:alert_id, :t, :type, :meta::jsonb)
            """
            ),
            {
                "alert_id": alert_id,
                "t": _now(),
                "type": type_,
                "meta": json.dumps(meta or {}),
            },
        )


async def list_alerts(resident_id: str | None = None) -> list[dict[str, Any]]:
    """List alerts from PostgreSQL care.alerts table."""
    query = """
        SELECT id, resident_id, kind, severity, note, created_at, status, ack_at, resolved_at
        FROM care.alerts
    """
    params = {}
    if resident_id:
        query += " WHERE resident_id = :resident_id"
        params["resident_id"] = resident_id
    query += " ORDER BY created_at DESC"

    with sync_engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row) for row in result.mappings()]


async def upsert_device(
    device_id: str, resident_id: str, *, battery_pct: int | None = None
) -> dict[str, Any]:
    """Upsert device in PostgreSQL care.devices table."""
    now = _now()

    with sync_engine.begin() as conn:
        # Try to fetch current device
        result = conn.execute(
            text(
                """
                SELECT id, resident_id, last_seen, battery_pct, battery_low_since,
                       battery_notified, offline_since, offline_notified
                FROM care.devices WHERE id = :device_id
            """
            ),
            {"device_id": device_id},
        )
        row = result.mappings().first()

        if not row:
            # Insert new device
            conn.execute(
                text(
                    """
                    INSERT INTO care.devices (id, resident_id, last_seen, battery_pct)
                    VALUES (:id, :resident_id, :last_seen, :battery_pct)
                """
                ),
                {
                    "id": device_id,
                    "resident_id": resident_id,
                    "last_seen": now,
                    "battery_pct": battery_pct,
                },
            )
            return {
                "id": device_id,
                "resident_id": resident_id,
                "last_seen": now,
                "battery_pct": battery_pct,
                "battery_low_since": None,
                "battery_notified": 0,
                "offline_since": None,
                "offline_notified": 0,
            }

        # Update existing device
        current_batt = row["battery_pct"]
        batt = battery_pct if battery_pct is not None else current_batt
        batt_low_since = row["battery_low_since"]
        batt_notified = row["battery_notified"]
        off_since = row["offline_since"]
        off_notified = row["offline_notified"]

        if batt is not None and batt < 15:
            batt_low_since = batt_low_since or now
        else:
            batt_low_since = None
            batt_notified = 0

        # Update device
        conn.execute(
            text(
                """
                UPDATE care.devices
                SET resident_id = :resident_id, last_seen = :last_seen,
                    battery_pct = :battery_pct, battery_low_since = :battery_low_since,
                    battery_notified = :battery_notified, offline_since = :offline_since,
                    offline_notified = :offline_notified
                WHERE id = :device_id
            """
            ),
            {
                "resident_id": resident_id,
                "last_seen": now,
                "battery_pct": batt,
                "battery_low_since": batt_low_since,
                "battery_notified": batt_notified,
                "offline_since": off_since,
                "offline_notified": off_notified,
                "device_id": device_id,
            },
        )

        return {
            "id": device_id,
            "resident_id": resident_id,
            "last_seen": now,
            "battery_pct": batt,
            "battery_low_since": batt_low_since,
            "battery_notified": batt_notified,
            "offline_since": off_since,
            "offline_notified": off_notified,
        }


async def get_device(device_id: str) -> dict[str, Any] | None:
    """Get device from PostgreSQL care.devices table."""
    with sync_engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, resident_id, last_seen, battery_pct, battery_low_since,
                       battery_notified, offline_since, offline_notified
                FROM care.devices WHERE id = :device_id
            """
            ),
            {"device_id": device_id},
        )
        row = result.mappings().first()
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
        return dict(row)


async def set_device_flags(device_id: str, **flags: Any) -> None:
    """Update device flags in PostgreSQL care.devices table."""
    if not flags:
        return
    # Build dynamic UPDATE query
    set_clause = ", ".join(f"{k} = :{k}" for k in flags)
    params = {**flags, "device_id": device_id}

    with sync_engine.begin() as conn:
        conn.execute(
            text(f"UPDATE care.devices SET {set_clause} WHERE id = :device_id"), params
        )


async def list_devices() -> list[dict[str, Any]]:
    """List all devices from PostgreSQL care.devices table."""
    with sync_engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, resident_id, last_seen, battery_pct, battery_low_since,
                       battery_notified, offline_since, offline_notified
                FROM care.devices
            """
            )
        )
        return [dict(row) for row in result.mappings()]


# TV Config -------------------------------------------------------------------


async def get_tv_config(resident_id: str) -> dict[str, Any] | None:
    """Get TV config from PostgreSQL care.tv_config table."""
    with sync_engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT resident_id, ambient_rotation, rail, quiet_hours, default_vibe, updated_at
                FROM care.tv_config WHERE resident_id = :resident_id
            """
            ),
            {"resident_id": resident_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return {
            "resident_id": row["resident_id"],
            "ambient_rotation": row["ambient_rotation"],
            "rail": row["rail"],
            "quiet_hours": json.loads(row["quiet_hours"] or "{}"),
            "default_vibe": row["default_vibe"],
            "updated_at": row["updated_at"],
        }


async def set_tv_config(
    resident_id: str,
    *,
    ambient_rotation: int,
    rail: str,
    quiet_hours: dict[str, Any] | None,
    default_vibe: str,
) -> None:
    """Upsert TV config in PostgreSQL care.tv_config table."""
    now = _now()
    qh = json.dumps(quiet_hours or {})

    with sync_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO care.tv_config (resident_id, ambient_rotation, rail, quiet_hours, default_vibe, updated_at)
                VALUES (:resident_id, :ambient_rotation, :rail, :quiet_hours::jsonb, :default_vibe, :updated_at)
                ON CONFLICT (resident_id) DO UPDATE SET
                    ambient_rotation = EXCLUDED.ambient_rotation,
                    rail = EXCLUDED.rail,
                    quiet_hours = EXCLUDED.quiet_hours,
                    default_vibe = EXCLUDED.default_vibe,
                    updated_at = EXCLUDED.updated_at
            """
            ),
            {
                "resident_id": resident_id,
                "ambient_rotation": int(ambient_rotation),
                "rail": str(rail),
                "quiet_hours": qh,
                "default_vibe": str(default_vibe),
                "updated_at": now,
            },
        )


# Sessions --------------------------------------------------------------------


async def create_session(rec: dict[str, Any]) -> None:
    """Create session in PostgreSQL care.care_sessions table."""
    now = _now()
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO care.care_sessions (id, resident_id, title, transcript_uri, status, created_at, updated_at)
                VALUES (:id, :resident_id, :title, :transcript_uri, :status, :created_at, :updated_at)
            """
            ),
            {
                "id": rec["id"],
                "resident_id": rec["resident_id"],
                "title": rec.get("title", ""),
                "transcript_uri": rec.get("transcript_uri"),
                "status": rec.get("status", "active"),
                "created_at": now,
                "updated_at": now,
            },
        )


async def update_session(session_id: str, **fields: Any) -> None:
    """Update session in PostgreSQL care.care_sessions table."""
    if not fields:
        return
    fields["updated_at"] = _now()
    # Build dynamic UPDATE query
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "session_id": session_id}

    with sync_engine.begin() as conn:
        conn.execute(
            text(f"UPDATE care.care_sessions SET {set_clause} WHERE id = :session_id"),
            params,
        )


async def list_sessions(resident_id: str | None = None) -> list[dict[str, Any]]:
    """List sessions from PostgreSQL care.care_sessions table."""
    query = """
        SELECT id, resident_id, title, transcript_uri, status, created_at, updated_at
        FROM care.care_sessions
    """
    params = {}
    if resident_id:
        query += " WHERE resident_id = :resident_id"
        params["resident_id"] = resident_id
    query += " ORDER BY created_at DESC"

    with sync_engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row) for row in result.mappings()]


async def create_contact(rec: dict[str, Any]) -> None:
    """Create contact in PostgreSQL care.contacts table."""
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO care.contacts (id, resident_id, name, phone, priority, quiet_hours)
                VALUES (:id, :resident_id, :name, :phone, :priority, :quiet_hours::jsonb)
            """
            ),
            {
                "id": rec["id"],
                "resident_id": rec["resident_id"],
                "name": rec["name"],
                "phone": rec.get("phone"),
                "priority": int(rec.get("priority", 0)),
                "quiet_hours": json.dumps(rec.get("quiet_hours") or {}),
            },
        )


async def list_contacts(resident_id: str) -> list[dict[str, Any]]:
    """List contacts from PostgreSQL care.contacts table."""
    with sync_engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, resident_id, name, phone, priority, quiet_hours
                FROM care.contacts
                WHERE resident_id = :resident_id
                ORDER BY priority DESC
            """
            ),
            {"resident_id": resident_id},
        )
        contacts = []
        for row in result.mappings():
            contacts.append(
                {
                    "id": row["id"],
                    "resident_id": row["resident_id"],
                    "name": row["name"],
                    "phone": row["phone"],
                    "priority": row["priority"],
                    "quiet_hours": json.loads(row["quiet_hours"] or "{}"),
                }
            )
        return contacts


async def update_contact(contact_id: str, **fields: Any) -> None:
    """Update contact in PostgreSQL care.contacts table."""
    if not fields:
        return
    if "quiet_hours" in fields and isinstance(fields["quiet_hours"], dict | list):
        fields["quiet_hours"] = json.dumps(fields["quiet_hours"])
    # Build dynamic UPDATE query
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "contact_id": contact_id}

    with sync_engine.begin() as conn:
        conn.execute(
            text(f"UPDATE care.contacts SET {set_clause} WHERE id = :contact_id"),
            params,
        )


async def delete_contact(contact_id: str) -> None:
    """Delete contact from PostgreSQL care.contacts table."""
    with sync_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM care.contacts WHERE id = :contact_id"),
            {"contact_id": contact_id},
        )
