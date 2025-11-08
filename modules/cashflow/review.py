# modules/cashflow/review.py
import streamlit as st
from core.db import conn

def _list_events_for_day(day_iso: str):
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, name, status FROM events WHERE event_date=? ORDER BY created_at DESC, id DESC",
            (day_iso,),
        ).fetchall()

def _load_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, event_date, name, status, created_by, created_at, approved_by, approved_at "
            "FROM events WHERE id=?",
            (event_id,),
        ).fetchone()

def render_cashflow_review():
    st.subheader("🗂️ Review & Freigabe")

    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event aktiv. Wähle im Tab **Übersicht** ein Event oder lege eines an.")
        return

    row = _load_event(ev_id)
    if not row:
        st.warning("Event nicht gefunden. Wähle im Tab **Übersicht** ein Event.")
        return

    _id, ev_day, ev_name, ev_status, created_by, created_at, approved_by, approved_at = row
    st.markdown(f"**Event:** {ev_name}  \n**Datum:** {ev_day}  \n**Status:** {ev_status}")

    st.divider()
    st.caption("Hier kannst du die Tagessummen und ggf. Details darstellen (Summen je Einheit etc.). "
               "Die eigentliche Freigabe-Logik kannst du hier ergänzen (Statuswechsel, Locks, Audit-Log).")
