# modules/cashflow/home.py
import streamlit as st
import datetime
from typing import Dict, List, Tuple, Optional
from core.db import conn

# -------- Meta / Counts ----------
_META_UNIT_KEYS = {
    "bars": ["bars_count", "business_bars", "num_bars"],
    "registers": ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

def _get_counts() -> Dict[str, int]:
    def _first_int(keys: List[str], default: int = 0) -> int:
        for k in keys:
            v = _get_meta(k)
            if v is not None and str(v).strip() != "":
                try:
                    return max(0, int(float(str(v).strip())))
                except Exception:
                    continue
        return default
    return {
        "bars": _first_int(_META_UNIT_KEYS["bars"], 0),
        "registers": _first_int(_META_UNIT_KEYS["registers"], 0),
        "cloakrooms": _first_int(_META_UNIT_KEYS["cloakrooms"], 0),
    }

# -------- Events ----------
def _ensure_event_schema():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',  -- open | approved | closed
                created_by TEXT,
                created_at TEXT,
                approved_by TEXT,
                approved_at TEXT
            )
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name
            ON events(event_date, name)
        """)
        cn.commit()

def _get_or_create_event(day: datetime.date, name: str, username: str) -> int:
    _ensure_event_schema()
    day_str = day.isoformat()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT id FROM events WHERE event_date=? AND name=?",
            (day_str, name.strip()),
        ).fetchone()
        if row:
            return row[0]
        c.execute(
            "INSERT INTO events(event_date, name, status, created_by, created_at) VALUES(?,?,?,?,?)",
            (day_str, name.strip(), "open", username, datetime.datetime.now().isoformat(timespec="seconds")),
        )
        cn.commit()
        return c.lastrowid

def _get_event(event_id: int) -> Optional[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, event_date, name, status, created_by, created_at, approved_by, approved_at "
            "FROM events WHERE id=?", (event_id,)
        ).fetchone()

# -------- Units / Rechte ----------
def _decode_units(units: str) -> Dict[str, List[int]]:
    out = {"bar": [], "cash": [], "cloak": []}
    if not units:
        return out
    for token in [t.strip() for t in units.split(",") if t.strip()]:
        if ":" not in token:
            continue
        t, v = token.split(":", 1)
        try:
            n = int(v)
        except Exception:
            continue
        if t in out and n not in out[t]:
            out[t].append(n)
    for k in out:
        out[k] = sorted(out[k])
    return out

def _get_user(username: str) -> Optional[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, username, functions, units FROM users WHERE username=?",
            (username,),
        ).fetchone()

def _user_rights(username: str, session_role: str = "") -> Dict:
    row = _get_user(username)
    if not row:
        return {"is_mgr": session_role.lower() == "admin", "units": {"bar": [], "cash": [], "cloak": []}}
    _, _, functions, units = row
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    is_mgr = ("admin" in funcs) or ("betriebsleiter" in funcs) or (session_role.lower() == "admin")
    return {"is_mgr": is_mgr, "units": _decode_units(units or "")}

# -------- Tiles ----------
def _tile(title: str, subtitle: str, key: str) -> bool:
    with st.container(border=True):
        st.markdown(f"**{title}**  \n"
                    f"<span style='opacity:.7;font-size:12px'>{subtitle}</span>",
                    unsafe_allow_html=True)
        return st.button("Öffnen", key=key, use_container_width=True)

def _render_tiles(event_id: int, rights: Dict, counts: Dict[str, int]):
    is_mgr = rights["is_mgr"]
    allowed = rights["units"]

    def _visible(unit_type: str, i: int) -> bool:
        return True if is_mgr else (i in allowed.get(unit_type, []))

    # Bars
    if counts["bars"]:
        st.caption("Bars")
        cols = st.columns(min(4, max(1, counts["bars"])))
        ci = 0
        for i in range(1, counts["bars"]+1):
            if not _visible("bar", i):
                continue
            with cols[ci]:
                if _tile(f"Bar {i}", "Umsatz & Voucher erfassen", key=f"open_bar_{event_id}_{i}"):
                    st.session_state["cf_unit"] = ("bar", i)
                    st.rerun()
            ci = (ci + 1) % len(cols)

    # Kassen
    if counts["registers"]:
        st.caption("Kassen")
        cols = st.columns(min(4, max(1, counts["registers"])))
        ci = 0
        for i in range(1, counts["registers"]+1):
            if not _visible("cash", i):
                continue
            with cols[ci]:
                if _tile(f"Kassa {i}", "Bar/Unbar (Karten) erfassen", key=f"open_cash_{event_id}_{i}"):
                    st.session_state["cf_unit"] = ("cash", i)
                    st.rerun()
            ci = (ci + 1) % len(cols)

    # Garderoben
    if counts["cloakrooms"]:
        st.caption("Garderoben")
        cols = st.columns(min(4, max(1, counts["cloakrooms"])))
        ci = 0
        for i in range(1, counts["cloakrooms"]+1):
            if not _visible("cloak", i):
                continue
            with cols[ci]:
                if _tile(f"Garderobe {i}", "Jacken/Taschen erfassen", key=f"open_cloak_{event_id}_{i}"):
                    st.session_state["cf_unit"] = ("cloak", i)
                    st.rerun()
            ci = (ci + 1) % len(cols)

# -------- Public: Home ----------
def render_cashflow_home():
    """
    Zeigt:
    1) Event anlegen/öffnen (nur Betriebsleiter/Admin).
    2) Aktives Event (falls vorhanden).
    3) Kacheln für Einheiten.
    """
    username = st.session_state.get("username") or "unknown"
    role     = st.session_state.get("role") or "guest"

    rights = _user_rights(username, role)
    is_mgr = rights["is_mgr"]

    # 1) Event anlegen/öffnen (nur Manager)
    ev_id = st.session_state.get("cf_event_id")
    with st.expander("📅 Event anlegen/öffnen", expanded=(ev_id is None)):
        c1, c2, c3 = st.columns([1,2,1])
        day  = c1.date_input("Event-Datum", value=st.session_state.get("cf_day") or datetime.date.today(), key="cf_day")
        name = c2.text_input("Eventname", value=st.session_state.get("cf_name") or "", key="cf_name", placeholder="z. B. OZ / Halloween")

        if is_mgr:
            start = c3.button("▶️ Starten/Fortsetzen", type="primary", use_container_width=True, disabled=(not name or not day))
            if start:
                st.session_state["cf_event_id"] = _get_or_create_event(day, name, username)
                st.session_state["cf_name"] = name
                st.session_state.pop("cf_unit", None)
                st.rerun()
        else:
            st.caption("Nur Betriebsleiter/Admin können einen Tag starten. Bitte Eventname & Datum vom Betriebsleiter anlegen lassen.")

    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event/Tag vorhanden.")
        return

    evt = _get_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut starten.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status, _, created_at, approved_by, approved_at = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: **{ev_status}**)")

    counts = _get_counts()
    if counts["bars"] + counts["registers"] + counts["cloakrooms"] == 0:
        st.warning("Keine Einheiten (Bars/Kassen/Garderobe) konfiguriert – bitte im Admin-Bereich unter „Betrieb“ Anzahl hinterlegen.")
        return

    _render_tiles(ev_id, rights, counts)
