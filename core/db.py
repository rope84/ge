# core/db.py

import sqlite3
import shutil
import time
from pathlib import Path

DB_PATH = "gastro.db"
BACKUP_DIR = Path("DB_BCK")


# ---------- Low-level helpers ----------
def conn():
    """Öffnet eine SQLite-Verbindung (thread-safe off, passend für Streamlit)."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _table_has_column(c, table: str, col: str) -> bool:
    c.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in c.fetchall())


def _add_column_if_missing(c, table: str, col: str, ddl: str):
    if not _table_has_column(c, table, col):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


# ---------- Migrations ----------
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
    """Führt idempotente Migrationen durch."""
    with conn() as cn:
        c = cn.cursor()
        _ensure_schema_migrations(c)
        ver = _get_version(c)

        # USERS Tabelle
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT UNIQUE NOT NULL,
                passhash    TEXT NOT NULL,
                role        TEXT NOT NULL DEFAULT 'user',
                scope       TEXT DEFAULT '',
                email       TEXT DEFAULT '',
                first_name  TEXT DEFAULT '',
                last_name   TEXT DEFAULT ''
            );
        """)
        _add_column_if_missing(c, "users", "passhash", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(c, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
        _add_column_if_missing(c, "users", "scope", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "email", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "first_name", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "last_name", "TEXT DEFAULT ''")

        # EMPLOYEES Tabelle
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

        # SETUP Tabelle

        # SETUP Tabelle
        c.execute("""
            CREATE TABLE IF NOT EXISTS setup (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)


# DAILY Tabelle
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

        # Schema-Version setzen
        target_ver = 2
        if ver < target_ver:
            _set_version(c, target_ver)

        cn.commit()


# ---------- Setup ----------
def setup_db():
    """
    Initialisiert die Datenbank:
    - legt Datei und Backup-Verzeichnis an
    - sichert DB vor Migration
    - führt Migration durch
    """
    if not Path(DB_PATH).exists():
        Path(DB_PATH).touch()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_file = BACKUP_DIR / f"gastro.db.bak_{int(time.time())}"
    try:
        shutil.copyfile(DB_PATH, backup_file)
        print(f"[Backup] Datenbank gesichert als: {backup_file}")
    except Exception as e:
        print(f"[WARNUNG] Backup konnte nicht erstellt werden: {e}")

    migrate()
