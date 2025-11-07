# modules/cashflow/models.py
import json
import datetime
from typing import Optional, List, Dict, Any, Tuple
from core.db import conn

def ensure_cashflow_schema():
    with conn() as cn:
        c = cn.cursor()

        # Meta: Anzahl Bars/Kassen/Garderoben holst du aus admin.meta (kein neues Schema nötig)

        # Tages-Event (vom Betriebsleiter freigegeben/geschlossen)
        c.execute("""
            CREATE TABLE IF NOT EXISTS day_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                event_name TEXT NOT NULL,
                status TEXT NOT NULL,         -- DRAFT | OPEN | IN_PROGRESS | CLOSED
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                opened_at TEXT,
                closed_at TEXT
            )
        """)

        # Einheiten (Units) – Bars, Kassen, Garderoben – werden pro Betrieb geführt
        c.execute("""
            CREATE TABLE IF NOT EXISTS units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_type TEXT NOT NULL,      -- 'bar' | 'kassa' | 'cloak'
                unit_index INTEGER NOT NULL,  -- 1..N
                name TEXT NOT NULL            -- z.B. "Bar 1"
            )
        """)

        # Zuweisungen: welcher User ist Leiter welcher Unit?
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                unit_id INTEGER NOT NULL,
                UNIQUE(user_name, unit_id)
            )
        """)

        # Tages-Einträge je Event + Unit (generisch via JSON)
        c.execute("""
            CREATE TABLE IF NOT EXISTS day_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                unit_id INTEGER NOT NULL,
                owner_user TEXT,              -- wer hat den Eintrag angelegt
                data_json TEXT NOT NULL,      -- generisch: {'cash':..., 'pos1':..., 'voucher':...}
                total REAL NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(event_id, unit_id)
            )
        """)

        # Audit-Log
        c.execute("""
            CREATE TABLE IF NOT EXISTS day_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL DEFAULT (datetime('now')),
                actor TEXT,
                action TEXT,                  -- e.g. 'EVENT_OPEN','ENTRY_UPDATE','EVENT_CLOSE'
                target TEXT,                  -- 'event:<id>' / 'entry:<id>'
                diff_json TEXT                -- optional: {"before": {...}, "after": {...}}
            )
        """)

        cn.commit()

# ---- CRUD Helper ----

def create_event(event_date: str, event_name: str, created_by: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        c.execute("INSERT INTO day_events(event_date, event_name, status, created_by) VALUES(?,?,?,?)",
                  (event_date, event_name, "DRAFT", created_by))
        cn.commit()
        return c.lastrowid

def open_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE day_events SET status='IN_PROGRESS', opened_at=datetime('now') WHERE id=?", (event_id,))
        cn.commit()

def close_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE day_events SET status='CLOSED', closed_at=datetime('now') WHERE id=?", (event_id,))
        cn.commit()

def get_current_event() -> Optional[Dict[str,Any]]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id, event_date, event_name, status, created_by, created_at, opened_at, closed_at
            FROM day_events
            ORDER BY datetime(created_at) DESC
            LIMIT 1
        """).fetchone()
        if not row:
            return None
        keys = ["id","event_date","event_name","status","created_by","created_at","opened_at","closed_at"]
        return dict(zip(keys, row))

def list_units() -> List[Dict[str,Any]]:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("SELECT id, unit_type, unit_index, name FROM units ORDER BY unit_type, unit_index").fetchall()
        return [dict(zip(["id","unit_type","unit_index","name"], r)) for r in rows]

def upsert_unit(unit_type: str, unit_index: int, name: str):
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT id FROM units WHERE unit_type=? AND unit_index=?", (unit_type, unit_index)).fetchone()
        if row:
            c.execute("UPDATE units SET name=? WHERE id=?", (name, row[0]))
        else:
            c.execute("INSERT INTO units(unit_type, unit_index, name) VALUES(?,?,?)", (unit_type, unit_index, name))
        cn.commit()

def save_entry(event_id: int, unit_id: int, owner_user: str, data: Dict[str,Any], total: float, actor: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        j = json.dumps(data, ensure_ascii=False)
        # Prüfen, ob es schon einen Eintrag gibt
        row = c.execute("SELECT id, data_json FROM day_entries WHERE event_id=? AND unit_id=?", (event_id, unit_id)).fetchone()
        if row:
            before = row[1]
            c.execute("""
                UPDATE day_entries
                SET data_json=?, total=?, updated_by=?, updated_at=datetime('now')
                WHERE id=?
            """, (j, float(total), actor, row[0]))
            entry_id = row[0]
            _insert_audit(actor, "ENTRY_UPDATE", f"entry:{entry_id}", before, j, cn)
        else:
            c.execute("""
                INSERT INTO day_entries(event_id, unit_id, owner_user, data_json, total, updated_by)
                VALUES (?,?,?,?,?,?)
            """, (event_id, unit_id, owner_user, j, float(total), actor))
            entry_id = c.lastrowid
            _insert_audit(actor, "ENTRY_CREATE", f"entry:{entry_id}", None, j, cn)
        cn.commit()
        return entry_id

def get_entry(event_id: int, unit_id: int) -> Optional[Dict[str,Any]]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id, owner_user, data_json, total, updated_by, updated_at
            FROM day_entries WHERE event_id=? AND unit_id=?
        """, (event_id, unit_id)).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "owner_user": row[1],
            "data": json.loads(row[2]),
            "total": row[3],
            "updated_by": row[4],
            "updated_at": row[5],
        }

def assign_user_to_unit(user_name: str, unit_id: int):
    with conn() as cn:
        c = cn.cursor()
        c.execute("INSERT OR IGNORE INTO user_units(user_name, unit_id) VALUES(?,?)", (user_name, unit_id))
        cn.commit()

def user_units(user_name: str) -> List[int]:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("SELECT unit_id FROM user_units WHERE user_name=?", (user_name,)).fetchall()
        return [r[0] for r in rows]

def _insert_audit(actor: str, action: str, target: str, before_json: Optional[str], after_json: Optional[str], cn):
    diff = None
    if before_json or after_json:
        diff = json.dumps({"before": json.loads(before_json) if before_json else None,
                           "after": json.loads(after_json) if after_json else None}, ensure_ascii=False)
    cur = cn.cursor()
    cur.execute("INSERT INTO day_audit(actor, action, target, diff_json) VALUES(?,?,?,?)", (actor, action, target, diff))
