"""SQLite connection, migration, backup and restore helpers (local file only)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'migrations'
DEFAULT_DB = ROOT / 'local' / 'deadlines.db'


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection in autocommit mode; callers manage transactions explicitly."""
    conn = sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 5000')
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
    if row is None:
        return 0
    return conn.execute('SELECT COALESCE(MAX(version), 0) FROM schema_migrations').fetchone()[0]


def migrate_up(conn: sqlite3.Connection) -> int:
    if schema_version(conn) >= 1:
        return 1
    conn.executescript('BEGIN;\n' + (MIGRATIONS / '001_up.sql').read_text(encoding='utf-8') + '\nCOMMIT;')
    return schema_version(conn)


def migrate_down(conn: sqlite3.Connection) -> int:
    conn.executescript('BEGIN;\n' + (MIGRATIONS / '001_down.sql').read_text(encoding='utf-8') + '\nCOMMIT;')
    return schema_version(conn)


def backup(conn: sqlite3.Connection, dest: str | Path) -> Path:
    """Consistent online copy using SQLite's backup API."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(str(dest))
    try:
        conn.backup(target)
    finally:
        target.close()
    return dest


def restore(backup_path: str | Path, db_path: str | Path) -> None:
    """Replace the live database contents with a backup (server must be stopped)."""
    source = sqlite3.connect(str(backup_path))
    target = sqlite3.connect(str(db_path))
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
