# modules/cashflow/home.py
import streamlit as st
import datetime
from typing import Dict, List, Optional, Tuple
from core.db import conn
from .utils import numbers_from_meta

# --- Schema / DB Helpers ------------------------------------------------------

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
        -- 1 Event-Name pro Tag ist zulässig, aber mehrere Events pro Tag mit unterschiedlichen Namen sind erlaubt
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date, name)")
        cn.commit()

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
            "VALUES(?,?,?,?,datetime('now'))",
            (day.isoformat(), name.strip(), "open", user),
        )
        cn.commit()
        return c.lastrowid

def _events_for_day(day: datetime.date) -> List[Tuple[int, str, str]]:
    """Return [(id, name, status), ...] for a given day."""
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            "SELECT id, name, status FROM events WHERE event_date=? ORDER BY created_at ASC",
            (day.isoformat(),),
        ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]

def _get_event(ev_id: int) -> Optional[Tuple[int, str, str, str]]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT id, event_date, name, status FROM events WHERE id=?",
            (ev_id,),
        ).fetchone()
        return row if row else None

# --- UI -----------------------------------------------------------------------

def render_cashflow_home(is_mgr: bool, is_bar: bool, is_kas: bool, is_clo: bool):
    st.subheader("🏁 Übersicht")

    # 1) Tag wählen (alle sehen das)
    col1, col2 = st.columns([1, 2])
    day = col1.date_input(
        "Event-Datum",
        value=st.session_state.get("cf_day") or datetime.date.today(),
        key="cf_day",
    )

    # 2) Event-Auswahl / Anlegen (Mgr kann anlegen, alle können auswählen)
    events = _events_for_day(day)
    names_with_labels = [f"{name}  ·  ({status})" for _, name, status in events]
    id_by_label = {f"{name}  ·  ({status})": ev_id for ev_id, name, status in events}

    # Aktives Event aus Session übernehmen, falls es zu diesem Tag passt
    active_ev_id = st.session_state.get("cf_event_id")

    # a) Manager: neues Event anlegen
    if is_mgr:
        with st.expander("➕ Neues Event am selben Tag anlegen", expanded=False):
            new_name = st.text_input("Eventname", key="cf_new_event_name", placeholder="z. B. OZ / Halloween Late Night")
            create = st.button("Event anlegen", type="primary", use_container_width=True, disabled=(not new_name))
            if create:
                ev_id = _get_or_create_event(day, new_name, st.session_state.get("username") or "unknown")
                st.session_state["cf_event_id"] = ev_id
                st.success(f"Event '{new_name}' angelegt und aktiviert.")
                st.rerun()

    # b) Event-Auswahl (wenn mehrere am Tag existieren)
    if events:
        sel_label = col2.selectbox(
            "Event auswählen",
            options=["— Bitte wählen —"] + names_with_labels,
            index=0,
            key="cf_event_selectbox",
        )
        if sel_label != "— Bitte wählen —":
            chosen_id = id_by_label[sel_label]
            # Nur umschalten, wenn anderes Event gewählt wurde
            if active_ev_id != chosen_id:
                st.session_state["cf_event_id"] = chosen_id
                st.success("Event gewechselt.")
                st.rerun()
    else:
        if is_mgr:
            st.info("Für diesen Tag gibt es noch kein Event. Lege oben eines an.")
        else:
            st.info("Kein Event/Tag vorhanden. Warte bis der Betriebsleiter ein Event öffnet.")

    # 3) Aktives Event anzeigen
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        return

    evt = _get_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut auswählen/öffnen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    # 4) Kacheln je Einheit (Rollen-basiert)
    cnt = numbers_from_meta()
    if cnt["bars"] + cnt["registers"] + cnt["cloakrooms"] == 0:
        st.warning("Keine Einheiten konfiguriert – bitte unter Admin → Betrieb definieren.")
        return

    def _tile(label: str, subtitle: str, key: str) -> bool:
        with st.container(border=True):
            st.markdown(
                f"**{label}**  \n"
                f"<span style='opacity:.7;font-size:12px'>{subtitle}</span>",
                unsafe_allow_html=True,
            )
            return st.button("Bearbeiten", key=key, use_container_width=True)

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
                    st.experimental_rerun()
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
                    st.experimental_rerun()
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
                    st.experimental_rerun()
            ci = (ci + 1) % len(cols)
