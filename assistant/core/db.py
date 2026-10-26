"""SQLite access: one connection per thread, WAL mode, numbered migrations."""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from assistant.core.config import PKG, get_settings

MIGRATIONS_DIR = PKG / "core" / "migrations"

_local = threading.local()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_path() -> Path:
    return get_settings().data_dir / "app.db"


def connect() -> sqlite3.Connection:
    """Return this thread's connection to the current database file.

    Autocommit mode (isolation_level=None): use explicit BEGIN ... COMMIT for multi-statement writes.
    """
    path = db_path()
    conns: dict[Path, sqlite3.Connection] = getattr(_local, "conns", None) or {}
    _local.conns = conns
    conn = conns.get(path)
    if conn is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conns[path] = conn
    return conn


def close_all() -> None:
    """Close this thread's connections (used by tests when switching data dirs)."""
    for conn in (getattr(_local, "conns", None) or {}).values():
        conn.close()
    _local.conns = {}


def init_db() -> None:
    conn = connect()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(f.name.split("_")[0])
        if version in applied:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_version VALUES (?, ?)", (version, now()))
