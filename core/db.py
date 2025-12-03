# core/db.py

import sqlite3
import shutil
import time
from pathlib import Path

DB_PATH = "gastro.db"
BACKUP_DIR = Path("DB_BCK")


def conn():
    """Öffnet eine SQLite-Verbindung (thread-safe off, passend für Streamlit)."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _table_has_column(c, table: str, col: str) -> bool:
    c.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in c.fetchall())


def _add_column_if_missing(c, table: str, col: str, ddl: str):
    if not _table_has_column(c, table, col):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _list_tables(c):
    return [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]


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

        # USERS
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                passhash TEXT NOT NULL,
                functions TEXT NOT NULL DEFAULT '',
                status TEXT DEFAULT 'active',
                email TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT ''
            );
        """)
        _add_column_if_missing(c, "users", "functions", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(c, "users", "status", "TEXT DEFAULT 'active'")
        _add_column_if_missing(c, "users", "email", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "first_name", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "last_name", "TEXT DEFAULT ''")

        # EMPLOYEES
        c.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                contract TEXT NOT NULL,
                hourly REAL NOT NULL DEFAULT 0,
                is_barlead INTEGER NOT NULL DEFAULT 0,
                bar_no INTEGER
            );
        """)

        # SETUP
        c.execute("""
            CREATE TABLE IF NOT EXISTS setup (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # DAILY
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

        _set_version(c, 3)

        # Diagnose-Ausgabe
        print("✅ Migration abgeschlossen")
        print(f"📦 Datenbank-Datei: {Path(DB_PATH).resolve()}")
        print(f"📊 Tabellen in DB: {_list_tables(c)}")

        cn.commit()


def setup_db():
    """Initialisiert die Datenbank und führt Migration durch."""
    if not Path(DB_PATH).exists():
        Path(DB_PATH).touch()
        print(f"🆕 Neue Datenbank erstellt: {DB_PATH}")
    else:
        print(f"📁 Bestehende DB verwendet: {DB_PATH}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_file = BACKUP_DIR / f"gastro.db.bak_{int(time.time())}"
    try:
        shutil.copyfile(DB_PATH, backup_file)
        print(f"💾 Backup gespeichert unter: {backup_file}")
    except Exception as e:
        print(f"[WARNUNG] Backup fehlgeschlagen: {e}")

    migrate()
