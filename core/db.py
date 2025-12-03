import sqlite3
import shutil
import time
from pathlib import Path

DB_PATH = "gastro.db"
BACKUP_DIR = Path("DB_BCK")


def conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _table_has_column(c, table: str, col: str) -> bool:
    c.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in c.fetchall())


def _add_column_if_missing(c, table: str, col: str, ddl: str):
    if not _table_has_column(c, table, col):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


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

        # USERS Tabelle
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                passhash TEXT NOT NULL,
                functions TEXT DEFAULT '',
                status TEXT DEFAULT 'active'
            );
        """)
        _add_column_if_missing(c, "users", "functions", "TEXT DEFAULT ''")
        _add_column_if_missing(c, "users", "status", "TEXT DEFAULT 'active'")

        # SETUP
        c.execute("""
            CREATE TABLE IF NOT EXISTS setup (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        _set_version(c, 1)
        cn.commit()


def setup_db():
    if not Path(DB_PATH).exists():
        Path(DB_PATH).touch()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(DB_PATH, BACKUP_DIR / f"gastro.db.bak_{int(time.time())}")
    except Exception as e:
        print(f"Backup-Fehler: {e}")

    migrate()
