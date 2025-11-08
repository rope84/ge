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

# ---------------- DB/Schema ----------------

def _ensure_schema():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open', -- open | approved | closed
                created_by TEXT,
                created_at TEXT,
                approved_by TEXT,
                approved_at TEXT
            )
        """)
        # Mehrere Events pro Tag erlaubt, aber (Tag, Name) ist eindeutig
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date, name)")
        cn.commit()

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

def _get_or_create_event(day: datetime.date, name: str, user: str) -> int:
    _ensure_schema()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT id FROM events WHERE event_date=? AND name=?",
            (day.isoformat(), name.strip()),
        ).fetchone()
        if row:
            return row[0]
        c.execute(
            "INSERT INTO events(event_date, name, status, created_by, created_at) "
            "VALUES(?,?,?,?, datetime('now'))",
            (day.isoformat(), name.strip(), "open", user),
        )
        cn.commit()
        return c.lastrowid

def _list_events_for_day(day: datetime.date):
    _ensure_schema()
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            "SELECT id, name, status FROM events WHERE event_date=? ORDER BY created_at DESC, id DESC",
            (day.isoformat(),),
        ).fetchall()
    return rows  # [(id, name, status), ...]

def _load_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, event_date, name, status FROM events WHERE id=?",
            (event_id,),
        ).fetchone()

# ---------------- UI ----------------

def _tile(label: str, subtitle: str, key: str) -> bool:
    with st.container(border=True):
        st.markdown(
            f"**{label}**  \n"
            f"<span style='opacity:.7;font-size:12px'>{subtitle}</span>",
            unsafe_allow_html=True
        )
        return st.button("Bearbeiten", key=key, use_container_width=True)

def render_cashflow_home(is_mgr: bool, is_bar: bool, is_kas: bool, is_clo: bool):
    st.subheader("🏁 Übersicht")

    # Event-Header
    default_day = st.session_state.get("cf_event_day") or datetime.date.today()
    default_name = st.session_state.get("cf_event_name") or ""

    col1, col2 = st.columns([1, 2])
    day = col1.date_input("Event-Datum", value=default_day, key="cf_day")
    name = col2.text_input("Eventname", value=default_name, key="cf_name", placeholder="z. B. OZ / Halloween")

    # Manager: Event öffnen/neu anlegen
    if is_mgr:
        open_col, _ = st.columns([1, 3])
        if open_col.button("▶️ Event öffnen/fortsetzen", type="primary", use_container_width=True, disabled=(not name or not day)):
            ev_id = _get_or_create_event(day, name, st.session_state.get("username") or "unknown")
            st.session_state["cf_event_id"]   = ev_id
            st.session_state["cf_event_day"]  = day
            st.session_state["cf_event_name"] = name
            st.success("Event aktiv.")
            st.rerun()
    else:
        st.caption("Event wird vom Betriebsleiter gestartet. Danach kannst du deine Einheit bearbeiten.")

    # Manager: Event-Auswahl (alle Events für gewählten Tag)
    if is_mgr:
        events_today = _list_events_for_day(day)
        if events_today:
            ev_labels = [f"{nm}  •  ({stt})" for (_id, nm, stt) in events_today]
            current_ev = st.session_state.get("cf_event_id")
            # Preselect aktuell aktives Event, falls es zum Datum gehört
            try:
                pre_idx = next(
                    (i for i, (eid, _, _) in enumerate(events_today) if eid == current_ev),
                    0
                )
            except Exception:
                pre_idx = 0
            sel_idx = st.selectbox("Event an diesem Tag auswählen", range(len(events_today)),
                                   format_func=lambda i: ev_labels[i], index=pre_idx)
            sel_id = events_today[sel_idx][0]
            col_a, col_b = st.columns([1, 1])
            if col_a.button("Aktivieren", use_container_width=True, key="btn_pick_event"):
                st.session_state["cf_event_id"]   = sel_id
                st.session_state["cf_event_day"]  = day
                st.session_state["cf_event_name"] = events_today[sel_idx][1]
                st.rerun()
        else:
            st.info("Für dieses Datum gibt es noch keine Events. Du kannst oben durch „Event öffnen/fortsetzen“ ein neues anlegen.")

    # Aktives Event
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event/Tag vorhanden.")
        return

    evt = _load_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut öffnen/aktivieren.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    # Einheiten-Kacheln
    cnt = _counts()
    if cnt["bars"] + cnt["registers"] + cnt["cloakrooms"] == 0:
        st.warning("Keine Einheiten konfiguriert – bitte unter Admin → Betrieb definieren.")
        return

    # Sichtbarkeiten: einfache Typen-Logik; (fein granular via Zuweisung machst du ggf. in utils)
    # Bars
    if is_mgr or is_bar:
        st.caption("Bars")
        cols = st.columns(min(4, max(1, cnt["bars"])))
        ci = 0
        for i in range(1, cnt["bars"] + 1):
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
        for i in range(1, cnt["registers"] + 1):
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
        for i in range(1, cnt["cloakrooms"] + 1):
            with cols[ci]:
                if _tile(f"Garderobe {i}", "Jacken/Taschen erfassen", key=f"cf_open_cloak_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cloak", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)
