# modules/cashflow/wizard.py
import streamlit as st
import datetime
from core.db import conn

def render_cashflow_wizard():
    """
    Wizard für Barleiter, Kassierer und Garderobenpersonal.
    Hier werden die Eingaben für ihre jeweilige Einheit gemacht.
    """
    st.header("🧭 Wizard – Abrechnung erfassen")

    # Prüfen, ob ein Event aktiv ist
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event angelegt. Bitte im Tab **Übersicht** oben den Tag starten.")
        return

    # Eventdaten laden
    with conn() as cn:
        c = cn.cursor()
        evt = c.execute(
            "SELECT id, event_date, name, status FROM events WHERE id=?", (ev_id,)
        ).fetchone()

    if not evt:
        st.warning("Event nicht gefunden – bitte im Tab Übersicht neu öffnen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    # Aktuelle Einheit merken oder neu wählen
    unit_sel = st.session_state.get("cf_unit")
    if not unit_sel:
        st.info("Bitte wähle deine Einheit über den Tab **Übersicht**.")
        return

    unit_type, unit_no = unit_sel
    st.write(f"Bearbeite Einheit: **{unit_type.upper()} #{unit_no}**")

    # Placeholder für tatsächliche Eingabelogik (kommt später)
    st.caption("Hier folgt die Eingabelogik für Umsätze, Voucher etc. (noch im Aufbau).")

    col1, col2 = st.columns(2)
    if col1.button("⬅️ Zurück zur Übersicht", use_container_width=True):
        st.session_state.pop("cf_unit", None)
        st.rerun()

    if col2.button("💾 Speichern", type="primary", use_container_width=True):
        st.success("Eingaben gespeichert (Demo).")
