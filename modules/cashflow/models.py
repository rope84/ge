# modules/cashflow/models.py
import datetime
from core.db import conn

def ensure_cashflow_schema():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date   TEXT NOT NULL,
                name         TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'open',  -- open|approved|closed
                created_by   TEXT,
                created_at   TEXT,
                approved_by  TEXT,
                approved_at  TEXT,
                bars_open INTEGER,
                registers_open INTEGER,
                cloakrooms_open INTEGER
            )
        """)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date, name)")
        # Migrations (falls Spalten fehlen)
        c.execute("PRAGMA table_info(events)")
        cols = {row[1] for row in c.fetchall()}
        for col in ("bars_open","registers_open","cloakrooms_open"):
            if col not in cols:
                c.execute(f"ALTER TABLE events ADD COLUMN {col} INTEGER")

        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id  INTEGER NOT NULL,
                unit_type TEXT NOT NULL,   -- bar|cash|cloak
                unit_no   INTEGER NOT NULL,
                field     TEXT NOT NULL,   -- cash,pos1,pos2,pos3,voucher,tables | card | coats_eur,bags_eur
                value     REAL  NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TEXT,
                UNIQUE(event_id, unit_type, unit_no, field)
            )
        """)
        cn.commit()

def list_events_for_day(day_str: str):
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, name, status, bars_open, registers_open, cloakrooms_open "
            "FROM events WHERE event_date=? ORDER BY created_at DESC, id DESC",
            (day_str,)
        ).fetchall()

def get_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, event_date, name, status, bars_open, registers_open, cloakrooms_open "
            "FROM events WHERE id=?",
            (event_id,)
        ).fetchone()

def get_or_create_event(day_str: str, name: str, user: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT id FROM events WHERE event_date=? AND name=?", (day_str, name.strip())).fetchone()
        if row:
            return row[0]
        c.execute(
            "INSERT INTO events(event_date, name, status, created_by, created_at) "
            "VALUES(?,?,?,?, datetime('now'))",
            (day_str, name.strip(), "open", user),
        )
        cn.commit()
        return c.lastrowid

def save_event_counts(event_id: int, bars: int, regs: int, cloaks: int):
    with conn() as cn:
        c = cn.cursor()
        c.execute(
            "UPDATE events SET bars_open=?, registers_open=?, cloakrooms_open=? WHERE id=?",
            (bars, regs, cloaks, event_id),
        )
        cn.commit()

def delete_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        c.execute("DELETE FROM cashflow_item WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM events WHERE id=?", (event_id,))
        cn.commit()

def unit_has_entries(event_id: int, unit_type: str, unit_no: int) -> bool:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute(
            "SELECT 1 FROM cashflow_item WHERE event_id=? AND unit_type=? AND unit_no=? LIMIT 1",
            (event_id, unit_type, unit_no)
        ).fetchone()
    return bool(r)
