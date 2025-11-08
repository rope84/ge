# modules/cashflow/models.py
import datetime
from typing import Optional, Dict, List, Tuple
from core.db import conn

# Einheitentypen konsistent halten
UNIT_TYPES = ("bar", "cash", "cloak")

def ensure_cashflow_schema():
    with conn() as cn:
        c = cn.cursor()

        # Events
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_date TEXT NOT NULL,
              name TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'open',   -- open | approved | closed
              created_by TEXT,
              created_at TEXT,
              approved_by TEXT,
              approved_at TEXT
            )
        """)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date,name)")

        # Event-Einheiten (aktiv & Status je Einheit)
        c.execute("""
            CREATE TABLE IF NOT EXISTS event_units (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id INTEGER NOT NULL,
              unit_type TEXT NOT NULL,               -- bar | cash | cloak
              unit_no   INTEGER NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 1,  -- 1=aktiv an diesem Tag
              is_done   INTEGER NOT NULL DEFAULT 0,  -- 1=Abrechnung erledigt
              done_by   TEXT,
              done_at   TEXT,
              UNIQUE(event_id, unit_type, unit_no)
            )
        """)

        # Einzelwerte (wie bisher)
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_item (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id  INTEGER NOT NULL,
              unit_type TEXT NOT NULL,
              unit_no   INTEGER NOT NULL,
              field     TEXT NOT NULL,               -- cash,pos1,pos2,pos3,voucher,tables | cash,card | coats_eur,bags_eur
              value     REAL NOT NULL DEFAULT 0,
              updated_by TEXT,
              updated_at TEXT,
              UNIQUE(event_id, unit_type, unit_no, field)
            )
        """)

        # Audit (kurz)
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              user TEXT,
              action TEXT,
              details TEXT
            )
        """)

        cn.commit()

def audit(user: str, action: str, details: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("INSERT INTO audit_log(ts,user,action,details) VALUES(?,?,?,?)",
                  (datetime.datetime.now().isoformat(timespec="seconds"), user, action, details))
        cn.commit()

# --- Meta Helpers ---
def get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def get_meta_int_any(keys: List[str], dflt: int = 0) -> int:
    for k in keys:
        v = get_meta(k)
        if v is not None and str(v).strip() != "":
            try:
                return max(0, int(float(str(v).strip())))
            except Exception:
                continue
    return dflt

META_KEYS = {
    "bars":       ["bars_count", "business_bars", "num_bars"],
    "registers":  ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

def meta_caps() -> Dict[str,int]:
    return {
        "bars":       get_meta_int_any(META_KEYS["bars"], 0),
        "registers":  get_meta_int_any(META_KEYS["registers"], 0),
        "cloakrooms": get_meta_int_any(META_KEYS["cloakrooms"], 0),
    }

# --- Event CRUD ---
def get_or_create_event(day, name: str, username: str) -> int:
    day_s = day.isoformat()
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT id FROM events WHERE event_date=? AND name=?", (day_s, name.strip())).fetchone()
        if r:
            return r[0]
        c.execute(
            "INSERT INTO events(event_date,name,status,created_by,created_at) VALUES(?,?,?,?,?)",
            (day_s, name.strip(), "open", username, datetime.datetime.now().isoformat(timespec="seconds"))
        )
        cn.commit()
        eid = c.lastrowid
    audit(username, "event_create", f"{day_s} | {name}")
    return eid

def list_events_for_day(day) -> List[Tuple[int,str,str]]:
    day_s = day.isoformat()
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            "SELECT id,name,status FROM events WHERE event_date=? ORDER BY id ASC", (day_s,)
        ).fetchall()
    return rows

def get_event(eid: int):
    with conn() as cn:
        c = cn.cursor()
        return c.execute("SELECT id,event_date,name,status,created_by,created_at,approved_by,approved_at FROM events WHERE id=?",
                         (eid,)).fetchone()

def delete_event_if_open(eid: int) -> bool:
    with conn() as cn:
        c = cn.cursor()
        st = c.execute("SELECT status FROM events WHERE id=?", (eid,)).fetchone()
        if not st or st[0] != "open":
            return False
        c.execute("DELETE FROM cashflow_item WHERE event_id=?", (eid,))
        c.execute("DELETE FROM event_units WHERE event_id=?", (eid,))
        c.execute("DELETE FROM events WHERE id=?", (eid,))
        cn.commit()
    return True

def approve_event(eid: int, user: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE events SET status='approved', approved_by=?, approved_at=? WHERE id=?",
                  (user, datetime.datetime.now().isoformat(timespec="seconds"), eid))
        cn.commit()
    audit(user, "event_approve", f"{eid}")

# --- Event Units ---
def upsert_event_units(eid: int, bars: int, regs: int, cloaks: int, user: str):
    with conn() as cn:
        c = cn.cursor()
        # Lösche existierende Einträge und setze neu (klare Quelle)
        c.execute("DELETE FROM event_units WHERE event_id=?", (eid,))
        # Bars
        for i in range(1, bars+1):
            c.execute("INSERT INTO event_units(event_id,unit_type,unit_no,is_active) VALUES(?,?,?,1)", (eid, "bar", i))
        # Kassen
        for i in range(1, regs+1):
            c.execute("INSERT INTO event_units(event_id,unit_type,unit_no,is_active) VALUES(?,?,?,1)", (eid, "cash", i))
        # Garderoben
        for i in range(1, cloaks+1):
            c.execute("INSERT INTO event_units(event_id,unit_type,unit_no,is_active) VALUES(?,?,?,1)", (eid, "cloak", i))
        cn.commit()
    audit(user, "event_units_set", f"{eid} -> bars={bars},regs={regs},cloaks={cloaks}")

def list_active_units(eid: int) -> List[Tuple[str,int,int]]:
    # return [(type, no, is_done)]
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT unit_type, unit_no, is_done
            FROM event_units
            WHERE event_id=? AND is_active=1
            ORDER BY unit_type, unit_no
        """, (eid,)).fetchall()
    return [(r[0], int(r[1]), int(r[2])) for r in rows]

def mark_unit_done(eid: int, utype: str, uno: int, done: bool, user: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
           UPDATE event_units
           SET is_done=?, done_by=?, done_at=?
           WHERE event_id=? AND unit_type=? AND unit_no=? AND is_active=1
        """, (1 if done else 0, user if done else None,
              datetime.datetime.now().isoformat(timespec="seconds") if done else None,
              eid, utype, uno))
        cn.commit()
    audit(user, "unit_done_toggle", f"{eid} {utype}#{uno} -> {done}")
