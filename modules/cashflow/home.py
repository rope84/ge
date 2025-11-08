# modules/cashflow/home.py
import streamlit as st
import datetime
from typing import Dict, List, Optional
from core.db import conn

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

def _counts() -> Dict[str, int]:
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

def _ensure_schema():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_by TEXT,
                created_at TEXT,
                approved_by TEXT,
                approved_at TEXT
            )
        """)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date, name)")
        cn.commit()

def _get_or_create_event(day: datetime.date, name: str, user: str) -> int:
    _ensure_schema()
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

def render_cashflow_home(is_mgr: bool, is_bar: bool, is_kas: bool, is_clo: bool):
    st.subheader("🏁 Übersicht")

    # Event wählen / anlegen (nur Betriebsleiter)
    col1, col2 = st.columns([1,2])
    day = col1.date_input("Event-Datum", value=st.session_state.get("cf_day") or datetime.date.today(), key="cf_day")
    name = col2.text_input("Eventname", value=st.session_state.get("cf_name") or "", key="cf_name")

    if is_mgr:
        if st.button("▶️ Event öffnen/fortsetzen", type="primary", use_container_width=True, disabled=(not name or not day)):
            ev_id = _get_or_create_event(day, name, st.session_state.get("username") or "unknown")
            st.session_state["cf_event_id"] = ev_id
            st.success("Event aktiv.")
            st.rerun()
    else:
        st.caption("Event wird vom Betriebsleiter freigegeben. Danach kannst du deine Einheit bearbeiten.")

    # Aktives Event anzeigen
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event/Tag vorhanden.")
        return

    with conn() as cn:
        c = cn.cursor()
        evt = c.execute("SELECT id, event_date, name, status FROM events WHERE id=?", (ev_id,)).fetchone()
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut öffnen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    # Kacheln je Einheit (nur sichtbare/zugewiesene)
    cnt = _counts()
    if cnt["bars"] + cnt["registers"] + cnt["cloakrooms"] == 0:
        st.warning("Keine Einheiten konfiguriert – bitte unter Admin → Betrieb definieren.")
        return

    def _tile(label: str, subtitle: str, key: str) -> bool:
        with st.container(border=True):
            st.markdown(f"**{label}**  \n<span style='opacity:.7;font-size:12px'>{subtitle}</span>", unsafe_allow_html=True)
            return st.button("Bearbeiten", key=key, use_container_width=True)

    # Sichtbarkeitslogik (einfach): Leiter sehen nur ihren Typ, Mgr alles
    # → Wenn du pro User noch konkrete Unit-Zuweisungen nutzt, ergänzen (units decoding).
    # Bars
    if is_mgr or is_bar:
        st.caption("Bars")
        cols = st.columns(min(4, max(1, cnt["bars"])))
        ci = 0
        for i in range(1, cnt["bars"]+1):
            with cols[ci]:
                if _tile(f"Bar {i}", "Umsatz & Voucher erfassen", key=f"cf_open_bar_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("bar", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)

    # Kassen
    if is_mgr or is_kas:
        st.caption("Kassen")
        cols = st.columns(min(4, max(1, cnt["registers"])))
        ci = 0
        for i in range(1, cnt["registers"]+1):
            with cols[ci]:
                if _tile(f"Kassa {i}", "Bar/Unbar (Karten) erfassen", key=f"cf_open_cash_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cash", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)

    # Garderoben
    if is_mgr or is_clo:
        st.caption("Garderoben")
        cols = st.columns(min(4, max(1, cnt["cloakrooms"])))
        ci = 0
        for i in range(1, cnt["cloakrooms"]+1):
            with cols[ci]:
                if _tile(f"Garderobe {i}", "Jacken/Taschen erfassen", key=f"cf_open_cloak_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cloak", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)
