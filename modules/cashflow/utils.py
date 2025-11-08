import datetime
from typing import Optional, Dict, List, Tuple
from core.db import conn

# ---------------- Meta Helpers ----------------

META_KEYS = {
    "bars": ["bars_count", "business_bars", "num_bars"],
    "registers": ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def counts_from_meta() -> Dict[str, int]:
    def _first_int(keys: List[str], dflt: int = 0) -> int:
        for k in keys:
            v = _get_meta(k)
            if v is not None and str(v).strip() != "":
                try:
                    return max(0, int(float(str(v).strip())))
                except Exception:
                    continue
        return dflt
    return {
        "bars": _first_int(META_KEYS["bars"], 0),
        "registers": _first_int(META_KEYS["registers"], 0),
        "cloakrooms": _first_int(META_KEYS["cloakrooms"], 0),
    }

def wardrobe_prices() -> Tuple[float, float]:
    def _f(name: str, dflt: float) -> float:
        v = _get_meta(name)
        try:
            return float(str(v).replace(",", ".")) if v is not None else dflt
        except Exception:
            return dflt
    return _f("conf_coat_price", 2.0), _f("conf_bag_price", 3.0)

# ---------------- Users / Functions ----------------

def user_has_function(username: str, func_name: str) -> bool:
    if not username:
        return False
    func_name = (func_name or "").strip().lower()
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT functions FROM users WHERE username=?", (username,)).fetchone()
    if not r or not r[0]:
        return False
    funcs = [f.strip().lower() for f in r[0].split(",") if f.strip()]
    return func_name in funcs

# ---------------- Schema / Events / Items ----------------

def ensure_base_schema():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',  -- open|approved|closed
                created_by TEXT,
                created_at TEXT,
                approved_by TEXT,
                approved_at TEXT
            )
        """)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date, name)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                unit_type TEXT NOT NULL,   -- bar|cash|cloak
                unit_no   INTEGER NOT NULL,
                field     TEXT NOT NULL,   -- cash,pos1,pos2,pos3,voucher,tables | cash,card | coats_eur,bags_eur
                value     REAL NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TEXT,
                UNIQUE(event_id, unit_type, unit_no, field)
            )
        """)
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

def get_events_for_day(day: datetime.date) -> List[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, name, status FROM events WHERE event_date=? ORDER BY id DESC",
            (day.isoformat(),)
        ).fetchall()

def create_or_get_event(day: datetime.date, name: str, user: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT id FROM events WHERE event_date=? AND name=?", (day.isoformat(), name.strip())).fetchone()
        if row:
            return row[0]
        c.execute(
            "INSERT INTO events(event_date, name, status, created_by, created_at) VALUES(?,?,?,?,datetime('now'))",
            (day.isoformat(), name.strip(), "open", user),
        )
        cn.commit()
        return c.lastrowid

def delete_event(ev_id: int):
    with conn() as cn:
        c = cn.cursor()
        c.execute("DELETE FROM cashflow_item WHERE event_id=?", (ev_id,))
        c.execute("DELETE FROM events WHERE id=?", (ev_id,))
        cn.commit()

def get_event(ev_id: int) -> Optional[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, event_date, name, status, created_by, created_at, approved_by, approved_at FROM events WHERE id=?",
            (ev_id,)
        ).fetchone()

def set_event_status(ev_id: int, status: str, username: str):
    with conn() as cn:
        c = cn.cursor()
        if status == "approved":
            c.execute(
                "UPDATE events SET status=?, approved_by=?, approved_at=datetime('now') WHERE id=?",
                (status, username, ev_id)
            )
        else:
            c.execute("UPDATE events SET status=? WHERE id=?", (status, ev_id))
        cn.commit()
