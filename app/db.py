"""
Centralized database initialization module.

This module provides a single function to initialize all database schemas
once during application startup, preventing redundant schema creation
during runtime operations.
"""

import asyncio
import logging
import os
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# Import database paths from various modules
from .auth import DB_PATH as AUTH_DB_PATH
from .auth_store import DB_PATH as AUTH_STORE_DB_PATH
from .care_store import DB_PATH as CARE_DB_PATH
from .music.store import DB_PATH as MUSIC_DB_PATH


async def init_db_once() -> None:
    """
    Initialize all database schemas once during application startup.

    This function consolidates all CREATE TABLE statements from various
    modules to ensure schemas are created only once at startup rather
    than repeatedly during runtime operations.
    """
    logger.info("Initializing database schemas...")

    # Initialize auth database schema
    await _init_auth_db()

    # Initialize auth store database schema
    await _init_auth_store_db()

    # Initialize care store database schema
    await _init_care_db()

    # Initialize music database schema
    await _init_music_db()

    logger.info("Database schemas initialized successfully")


async def _init_auth_db() -> None:
    """Initialize authentication database schema."""
    # Ensure directory exists for sqlite file paths
    try:
        p = Path(AUTH_DB_PATH)
        if p.parent and str(p).lower() not in {":memory:", ""}:
            p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    async with aiosqlite.connect(AUTH_DB_PATH) as db:
        # Set critical SQLite PRAGMAs once during initialization
        # journal_mode=WAL and synchronous=NORMAL persist in the database file
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        # Enable foreign key constraints - must be set on each connection
        await db.execute("PRAGMA foreign_keys=ON")

        # Create dedicated auth table to avoid collision with analytics 'users'
        await db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS auth (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )
        # Compatibility: create a minimal 'users' table if absent so tests can read it
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT
            )
            """
        )
        await db.commit()


async def _init_auth_store_db() -> None:
    """Initialize auth store database schema."""
    async with aiosqlite.connect(str(AUTH_STORE_DB_PATH)) as db:
        # Set critical SQLite PRAGMAs once during initialization
        # journal_mode=WAL and synchronous=NORMAL persist in the database file
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        # Enable foreign key constraints - must be set on each connection
        await db.execute("PRAGMA foreign_keys=ON")

        # users
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                name TEXT,
                avatar_url TEXT,
                created_at REAL NOT NULL,
                verified_at REAL,
                auth_providers TEXT
            )
            """
        )

        # devices
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_name TEXT,
                ua_hash TEXT NOT NULL,
                ip_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_seen_at REAL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        # sessions
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_seen_at REAL,
                revoked_at REAL,
                mfa_passed INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
            """
        )

        # auth_identities
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_identities (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_iss TEXT,
                provider_sub TEXT,
                email_normalized TEXT,
                email_verified INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(provider, provider_iss, provider_sub),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        # pat_tokens
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pat_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                scopes TEXT NOT NULL,
                exp_at REAL,
                created_at REAL NOT NULL,
                revoked_at REAL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )

        # audit_log
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                session_id TEXT,
                event_type TEXT NOT NULL,
                meta TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
            )
            """
        )

        await db.commit()


async def _init_care_db() -> None:
    """Initialize care store database schema."""
    async with aiosqlite.connect(str(CARE_DB_PATH)) as db:
        # Set critical SQLite PRAGMAs once during initialization
        # journal_mode=WAL and synchronous=NORMAL persist in the database file
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        # Enable foreign key constraints - must be set on each connection
        await db.execute("PRAGMA foreign_keys=ON")

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

        # Add indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_devices_resident ON devices(resident_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_devices_offline_notified ON devices(offline_notified, offline_since)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_devices_battery_notified ON devices(battery_notified, battery_low_since)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_alerts_resident_created ON alerts(resident_id, created_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_alert_events_alert_time ON alert_events(alert_id, t)")

        # Seed minimal test data
        await db.execute(
            "INSERT OR IGNORE INTO residents (id, name) VALUES (?, ?)",
            ("gigi", "Grandma Gigi")
        )
        await db.execute(
            """
            INSERT OR REPLACE INTO devices (
                id, resident_id, last_seen, battery_pct, battery_low_since, battery_notified, offline_since, offline_notified
            ) VALUES (?, ?, strftime('%s','now'), ?, NULL, 0, NULL, 0)
            """,
            ("tv-stick-1", "gigi", 18)
        )

        await db.commit()


async def _init_music_db() -> None:
    """Initialize music database schema."""
    async with aiosqlite.connect(MUSIC_DB_PATH) as db:
        # Set critical SQLite PRAGMAs once during initialization
        # journal_mode=WAL and synchronous=NORMAL persist in the database file
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        # Enable foreign key constraints - must be set on each connection
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_tokens (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                access_token BLOB NOT NULL,
                refresh_token BLOB,
                scope TEXT,
                expires_at INTEGER,
                updated_at INTEGER,
                PRIMARY KEY (user_id, provider)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_devices (
                provider TEXT NOT NULL,
                device_id TEXT NOT NULL,
                room TEXT,
                name TEXT,
                last_seen INTEGER,
                capabilities TEXT,
                PRIMARY KEY (provider, device_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_preferences (
                user_id TEXT PRIMARY KEY,
                default_provider TEXT,
                quiet_start TEXT DEFAULT '22:00',
                quiet_end TEXT DEFAULT '07:00',
                quiet_max_volume INTEGER DEFAULT 30,
                allow_explicit INTEGER DEFAULT 1
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS music_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                room TEXT,
                provider TEXT,
                device_id TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
            """
        )
        await db.commit()
