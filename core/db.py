from contextlib import contextmanager
import os
import sqlite3
import shutil
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("GE_DB_PATH", "ge.db")
BACKUP_DIR = os.getenv("GE_BACKUP_DIR", "DB_BCK")
BACKUP_KEEP = int(os.getenv("GE_BACKUPS_KEEP", "7"))


def get_db_path() -> str:
    return str(Path(DB_PATH).expanduser().resolve())


def get_backup_dir() -> str:
    return str(Path(BACKUP_DIR).expanduser().resolve())


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    db_file = get_db_path()
    try:
        cn = sqlite3.connect(db_file, check_same_thread=False)
    except Exception:
        logger.exception("Failed to connect to database at %s", db_file)
        raise
    try:
        yield cn
        try:
            cn.commit()
        except Exception:
            logger.exception("Failed to commit transaction")
    finally:
        try:
            cn.close()
        except Exception:
            logger.exception("Failed to close DB connection")


def _table_has_column(c, table: str, col: str) -> bool:
    c.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in c.fetchall())


def _add_column_if_missing(c, table: str, col: str, ddl: str):
    if not _table_has_column(c, table, col):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


# Migrations

def _ensure_schema_migrations(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations(
            id INTEGER PRIMARY KEY CHECK (id=1),
            version INTEGER NOT NULL
        )
    """)
    row = c.execute("SELECT version FROM schema_migrations WHERE id=1").fetchone()
    if row is None:
        c.execute("INSERT INTO schema_migrations(id, version) VALUES (1, 0)")


def _get_version(c) -> int:
    row = c.execute("SELECT version FROM schema_migrations WHERE id=1").fetchone()
    return row[0] if row else 0


def _set_version(c, v: int):
    c.execute("UPDATE schema_migrations SET version=? WHERE id=1", (v,))


def migrate():
    with conn() as cn:
        c = cn.cursor()
        _ensure_schema_migrations(c)
        ver = _get_version(c)

        # USERS table
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT UNIQUE NOT NULL,
                passhash    TEXT NOT NULL,
                functions   TEXT DEFAULT '',
                status      TEXT DEFAULT 'active',
                role        TEXT DEFAULT '',
                scope       TEXT DEFAULT '',
                email       TEXT DEFAULT '',
                first_name  TEXT DEFAULT '',
                last_name   TEXT DEFAULT ''
            );
        """)
        _add_column_if_missing(c, "users", "functions", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "status", "TEXT DEFAULT 'active'")
        _add_column_if_missing(c, "users", "role", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "scope", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "email", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "first_name", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "last_name", "TEXT DEFAULT ''")

        # EMPLOYEES table
        c.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                contract    TEXT NOT NULL,
                hourly      REAL NOT NULL DEFAULT 0,
                is_barlead  INTEGER NOT NULL DEFAULT 0,
                bar_no      INTEGER
            );
        """)

        # DAILY table
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datum TEXT NOT NULL UNIQUE,
                umsatz_total REAL NOT NULL DEFAULT 0,
                bar1 REAL NOT NULL DEFAULT 0,
                bar2 REAL NOT NULL DEFAULT 0,
                bar3 REAL NOT NULL DEFAULT 0,
                bar4 REAL NOT NULL DEFAULT 0,
                bar5 REAL NOT NULL DEFAULT 0,
                bar6 REAL NOT NULL DEFAULT 0,
                bar7 REAL NOT NULL DEFAULT 0,
                kasse1_cash REAL NOT NULL DEFAULT 0,
                kasse1_card REAL NOT NULL DEFAULT 0,
                kasse2_cash REAL NOT NULL DEFAULT 0,
                kasse2_card REAL NOT NULL DEFAULT 0,
                kasse3_cash REAL NOT NULL DEFAULT 0,
                kasse3_card REAL NOT NULL DEFAULT 0,
                garderobe_total REAL NOT NULL DEFAULT 0
            );
        """)

        # SETUP table
        c.execute("""
            CREATE TABLE IF NOT EXISTS setup (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # META table
        c.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # bump schema version if needed
        target_ver = 2
        if ver < target_ver:
            _set_version(c, target_ver)

        cn.commit()


def backup_db() -> Optional[str]:
    db_file = Path(get_db_path())
    if not db_file.exists():
        logger.info("Database file does not exist, skipping backup: %s", db_file)
        return None

    backup_dir = Path(get_backup_dir())
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed to create backup directory: %s", backup_dir)
        return None

    timestamp = int(time.time())
    backup_file = backup_dir / f"{db_file.name}.bak_{timestamp}"
    try:
        shutil.copy2(str(db_file), str(backup_file))
        logger.info("[Backup] Datenbank gesichert als: %s", backup_file)
    except Exception:
        logger.exception("[WARNUNG] Backup konnte nicht erstellt werden")
        return None

    # rotate
    try:
        backups = sorted([p for p in backup_dir.iterdir() if p.is_file() and p.name.startswith(db_file.name)], key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[BACKUP_KEEP:]:
            try:
                old.unlink()
            except Exception:
                logger.exception("Failed to remove old backup: %s", old)
    except Exception:
        logger.exception("Failed during backup rotation")

    return str(backup_file)


def setup_db():
    # ensure DB file exists and backups
    db_file = Path(get_db_path())
    if not db_file.exists():
        try:
            db_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        db_file.touch(exist_ok=True)

    backup_db()
    migrate()
