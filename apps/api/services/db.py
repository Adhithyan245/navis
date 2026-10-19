"""
services/db.py — the accounts database (accounts + synced user data).

Postgres when ACCOUNTS_DATABASE_URL is set (pooled; shared by every worker
and instance), otherwise a local SQLite file (ACCOUNTS_DB_PATH, default
apps/api/data/accounts.db). Callers write SQL with `?` placeholders and
the portable subset both engines understand (ON CONFLICT ... DO UPDATE).
Everything here is synchronous; callers run it via asyncio.to_thread.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from apps.api.core.config import settings

_init_lock = threading.Lock()
_initialised: set = set()
_pool = None

_SQLITE_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS accounts (
        id              TEXT PRIMARY KEY,
        email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name            TEXT,
        picture         TEXT,
        password_hash   TEXT,
        google_sub      TEXT UNIQUE,
        created_at      REAL NOT NULL,
        last_login_at   REAL
    )""",
    """CREATE TABLE IF NOT EXISTS user_data (
        user_id    TEXT NOT NULL,
        section    TEXT NOT NULL,
        payload    TEXT NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (user_id, section)
    )""",
    """CREATE TABLE IF NOT EXISTS push_devices (
        token      TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL,
        platform   TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_seen  REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS push_devices_user ON push_devices(user_id)",
    """CREATE TABLE IF NOT EXISTS push_prefs (
        user_id         TEXT PRIMARY KEY,
        safety_alerts   INTEGER NOT NULL DEFAULT 1,
        event_reminders INTEGER NOT NULL DEFAULT 1,
        updated_at      REAL NOT NULL
    )""",
)
# Columns added after the first release; ALTERed in when missing.
_SQLITE_ADDED = {"apple_sub": "TEXT", "session_version": "INTEGER NOT NULL DEFAULT 0"}

_PG_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS accounts (
        id              TEXT PRIMARY KEY,
        email           TEXT NOT NULL UNIQUE,
        name            TEXT,
        picture         TEXT,
        password_hash   TEXT,
        google_sub      TEXT UNIQUE,
        apple_sub       TEXT UNIQUE,
        session_version INTEGER NOT NULL DEFAULT 0,
        created_at      DOUBLE PRECISION NOT NULL,
        last_login_at   DOUBLE PRECISION
    )""",
    """CREATE TABLE IF NOT EXISTS user_data (
        user_id    TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        section    TEXT NOT NULL,
        payload    TEXT NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (user_id, section)
    )""",
    """CREATE TABLE IF NOT EXISTS push_devices (
        token      TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        platform   TEXT NOT NULL,
        created_at DOUBLE PRECISION NOT NULL,
        last_seen  DOUBLE PRECISION NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS push_devices_user ON push_devices(user_id)",
    """CREATE TABLE IF NOT EXISTS push_prefs (
        user_id         TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        safety_alerts   INTEGER NOT NULL DEFAULT 1,
        event_reminders INTEGER NOT NULL DEFAULT 1,
        updated_at      DOUBLE PRECISION NOT NULL
    )""",
)


def using_postgres() -> bool:
    return bool(settings.ACCOUNTS_DATABASE_URL)


def sqlite_path() -> Path:
    if settings.ACCOUNTS_DB_PATH:
        return Path(settings.ACCOUNTS_DB_PATH)
    return Path(__file__).resolve().parents[1] / "data" / "accounts.db"


class _PgConn:
    """psycopg connection that accepts `?` placeholders like sqlite3."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql.replace("?", "%s"), params)


def _get_pool():
    global _pool
    if _pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        _pool = ConnectionPool(settings.ACCOUNTS_DATABASE_URL, min_size=1, max_size=10,
                               kwargs={"row_factory": dict_row}, open=True)
    return _pool


def _init_sqlite(conn: sqlite3.Connection, path: str) -> None:
    with _init_lock:
        if path in _initialised:
            return
        for stmt in _SQLITE_SCHEMA:
            conn.execute(stmt)
        have = {r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        for col, decl in _SQLITE_ADDED.items():
            if col not in have:
                conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {decl}")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS accounts_apple_sub ON accounts(apple_sub)")
        conn.commit()
        _initialised.add(path)


@contextmanager
def connect() -> Iterator:
    """A connection that commits on success and rolls back on error."""
    if using_postgres():
        with _get_pool().connection() as conn:
            if "pg" not in _initialised:
                with _init_lock:
                    if "pg" not in _initialised:
                        for stmt in _PG_SCHEMA:
                            conn.execute(stmt)
                        conn.commit()
                        _initialised.add("pg")
            yield _PgConn(conn)
        return
    path = sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _init_sqlite(conn, str(path))
        with conn:
            yield conn
    finally:
        conn.close()


def ping() -> bool:
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:  # noqa: BLE001
        return False


def reset_for_tests() -> None:
    _initialised.clear()
