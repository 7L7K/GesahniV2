from __future__ import annotations

"""Minimal user model using ``sqlite3`` for tests.

The original project relied on SQLAlchemy which pulls in a fairly heavy
dependency chain.  For the unit tests we only need a tiny subset of the
functionality so this module provides a lightweight replacement implemented on
top of Python's built-in :mod:`sqlite3` module.
"""


import os
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("USERS_DB", "users.db")


def _connect() -> sqlite3.Connection:
    if DATABASE_URL.startswith("sqlite://"):
        path = DATABASE_URL[len("sqlite://") :]
        if path.startswith("/"):
            path = path[1:]
        return sqlite3.connect(path or ":memory:", check_same_thread=False)
    return sqlite3.connect(DATABASE_URL, check_same_thread=False)


_conn = _connect()
_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        login_count INTEGER DEFAULT 0,
        last_login TEXT
    )
    """
)
_conn.commit()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class User:
    id: int | None
    username: str
    hashed_password: str
    login_count: int = 0
    last_login: datetime | None = None


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def init_db() -> None:
    """No-op initialiser kept for API compatibility."""


@contextmanager
def get_session() -> Iterator[sqlite3.Connection]:
    """Yield the global connection as a context manager."""

    yield _conn


def _row_to_user(row: tuple) -> User:
    id_, username, pwd, count, last = row
    last_dt = datetime.fromisoformat(last) if last else None
    return User(
        id=id_,
        username=username,
        hashed_password=pwd,
        login_count=count,
        last_login=last_dt,
    )


def create_user(db: sqlite3.Connection, username: str, hashed_password: str) -> User:
    db.execute(
        "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
        (username, hashed_password),
    )
    db.commit()
    return get_user(db, username)  # type: ignore[return-value]


def get_user(db: sqlite3.Connection, username: str) -> User | None:
    cur = db.execute(
        "SELECT id, username, hashed_password, login_count, last_login FROM users WHERE username=?",
        (username,),
    )
    row = cur.fetchone()
    return _row_to_user(row) if row else None


def list_users(db: sqlite3.Connection) -> Iterable[User]:
    cur = db.execute(
        "SELECT id, username, hashed_password, login_count, last_login FROM users"
    )
    return [_row_to_user(r) for r in cur.fetchall()]


def update_login(db: sqlite3.Connection, user: User) -> User:
    user.login_count += 1
    user.last_login = datetime.now(UTC)
    db.execute(
        "UPDATE users SET login_count=?, last_login=? WHERE id=?",
        (user.login_count, user.last_login.isoformat(), user.id),
    )
    db.commit()
    return user


def delete_user(db: sqlite3.Connection, user: User) -> None:
    db.execute("DELETE FROM users WHERE id=?", (user.id,))
    db.commit()


__all__ = [
    "User",
    "init_db",
    "get_session",
    "create_user",
    "get_user",
    "list_users",
    "update_login",
    "delete_user",
]
