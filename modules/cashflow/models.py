import datetime
from typing import Dict, List, Optional, Tuple
from core.db import conn

# ----------------------------
# SCHEMA & BASIS
# ----------------------------
def ensure_cashflow_schema():
    with conn() as cn:
        c = cn.cursor()
        # Events
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date  TEXT NOT NULL,
                name        TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'open',  -- open|approved|closed
                created_by  TEXT,
                created_at  TEXT,
                approved_by TEXT,
                approved_at TEXT
            )
        """)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date, name)")

        # Erfasste Werte pro Einheit/Feld
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id  INTEGER NOT NULL,
                unit_type TEXT    NOT NULL,    -- bar|cash|cloak
                unit_no   INTEGER NOT NULL,
                field     TEXT    NOT NULL,    -- cash,pos1,pos2,pos3,voucher,tables | card | coats_eur,bags_eur
                value     REAL    NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TEXT,
                UNIQUE(event_id, unit_type, unit_no, field)
            )
        """)

        # „Fertig“-Status je Einheit
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_unit_status (
                event_id  INTEGER NOT NULL,
                unit_type TEXT    NOT NULL,
                unit_no   INTEGER NOT NULL,
                done_by   TEXT,
                done_at   TEXT,
                PRIMARY KEY (event_id, unit_type, unit_no)
            )
        """)

        # NEU: Event-spezifische Konfiguration der Einheiten
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_event_config (
                event_id    INTEGER PRIMARY KEY,
                bars        INTEGER NOT NULL DEFAULT 0,
                registers   INTEGER NOT NULL DEFAULT 0,
                cloakrooms  INTEGER NOT NULL DEFAULT 0,
                updated_by  TEXT,
                updated_at  TEXT
            )
        """)

        # Audit
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

# ----------------------------
# META-GRENZEN (Admin-Cockpit)
# ----------------------------
_META_UNIT_KEYS = {
    "bars":       ["bars_count", "business_bars", "num_bars"],
    "registers":  ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def _first_int(keys: List[str], dflt: int = 0) -> int:
    for k in keys:
        v = _get_meta(k)
        if v is not None and str(v).strip() != "":
            try:
                return max(0, int(float(str(v).strip())))
            except Exception:
                continue
    return dflt

def get_global_caps() -> Dict[str, int]:
    """Obergrenzen aus Admin-Cockpit."""
    return {
        "bars":       _first_int(_META_UNIT_KEYS["bars"], 0),
        "registers":  _first_int(_META_UNIT_KEYS["registers"], 0),
        "cloakrooms": _first_int(_META_UNIT_KEYS["cloakrooms"], 0),
    }

# ----------------------------
# EVENT-KONFIG (pro Event)
# ----------------------------
def get_event_config(event_id: int) -> Dict[str, int]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("""
            SELECT bars, registers, cloakrooms
            FROM cashflow_event_config WHERE event_id=?
        """, (event_id,)).fetchone()
    if r:
        return {"bars": int(r[0] or 0), "registers": int(r[1] or 0), "cloakrooms": int(r[2] or 0)}
    # Fallback: solange nichts gespeichert wurde → globale Obergrenzen
    return get_global_caps()

def upsert_event_config(event_id: int, bars: int, registers: int, cloakrooms: int, username: str):
    caps = get_global_caps()
    # Sicherheitskappung auf Admin-Grenzen
    bars       = max(0, min(int(bars),       caps["bars"]))
    registers  = max(0, min(int(registers),  caps["registers"]))
    cloakrooms = max(0, min(int(cloakrooms), caps["cloakrooms"]))

    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            INSERT INTO cashflow_event_config(event_id, bars, registers, cloakrooms, updated_by, updated_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(event_id)
            DO UPDATE SET bars=excluded.bars,
                          registers=excluded.registers,
                          cloakrooms=excluded.cloakrooms,
                          updated_by=excluded.updated_by,
                          updated_at=excluded.updated_at
        """, (event_id, bars, registers, cloakrooms, username, now))
        c.execute(
            "INSERT INTO audit_log(ts, user, action, details) VALUES(?,?,?,?)",
            (now, username, "event_config_upsert", f"event={event_id} bars={bars} registers={registers} cloakrooms={cloakrooms}")
        )
        cn.commit()

# praktische Helfer
def counts_for_event(event_id: int) -> Dict[str, int]:
    """Liefer die pro-Event-Zahlen, fällt sonst auf Admin-Grenzen zurück."""
    return get_event_config(event_id)

# ----------------------------
# EVENTS & LÖSCHEN
# ----------------------------
def create_or_get_event(day: datetime.date, name: str, username: str) -> int:
    ensure_cashflow_schema()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT id FROM events WHERE event_date=? AND name=?",
            (day.isoformat(), name.strip()),
        ).fetchone()
        if row:
            return int(row[0])
        now = datetime.datetime.now().isoformat(timespec="seconds")
        c.execute(
            "INSERT INTO events(event_date, name, status, created_by, created_at) VALUES(?,?,?,?,?)",
            (day.isoformat(), name.strip(), "open", username, now),
        )
        ev_id = c.lastrowid
        c.execute(
            "INSERT INTO audit_log(ts, user, action, details) VALUES(?,?,?,?)",
            (now, username, "event_create", f"{day.isoformat()} | {name}")
        )
        cn.commit()
        return int(ev_id)

def event_info(event_id: int) -> Optional[Tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute("SELECT id, event_date, name, status FROM events WHERE id=?", (event_id,)).fetchone()

def set_event_status(event_id: int, status: str, username: str):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        if status == "approved":
            c.execute(
                "UPDATE events SET status=?, approved_by=?, approved_at=? WHERE id=?",
                (status, username, now, event_id),
            )
        else:
            c.execute("UPDATE events SET status=? WHERE id=?", (status, event_id))
        c.execute(
            "INSERT INTO audit_log(ts, user, action, details) VALUES(?,?,?,?)",
            (now, username, "event_status", f"{event_id} -> {status}")
        )
        cn.commit()

def delete_event(event_id: int, username: str):
    """Komplettlöschen eines Events inkl. Items/Status/Config."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        c.execute("DELETE FROM cashflow_item WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM cashflow_unit_status WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM cashflow_event_config WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM events WHERE id=?", (event_id,))
        c.execute(
            "INSERT INTO audit_log(ts, user, action, details) VALUES(?,?,?,?)",
            (now, username, "event_delete", f"event={event_id}")
        )
        cn.commit()

# ----------------------------
# TOTALS / STATUS (für Übersichten)
# ----------------------------
def unit_total(event_id: int, unit_type: str, unit_no: int) -> float:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT field, value FROM cashflow_item
            WHERE event_id=? AND unit_type=? AND unit_no=?
        """, (event_id, unit_type, unit_no)).fetchall()
    vals = {k: 0.0 for k in ["cash","pos1","pos2","pos3","voucher","tables","card","coats_eur","bags_eur"]}
    for f, v in rows:
        try:
            vals[f] = float(v)
        except Exception:
            pass
    if unit_type == "bar":
        return vals["cash"] + vals["pos1"] + vals["pos2"] + vals["pos3"] + vals["voucher"]
    if unit_type == "cash":
        return vals["cash"] + vals["card"]
    return vals["coats_eur"] + vals["bags_eur"]

def unit_done(event_id: int, unit_type: str, unit_no: int) -> bool:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("""
            SELECT 1 FROM cashflow_unit_status
            WHERE event_id=? AND unit_type=? AND unit_no=?
        """, (event_id, unit_type, unit_no)).fetchone()
        return r is not None
