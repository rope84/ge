# modules/cashflow/cashflow.py

import streamlit as st
from core.db import conn
from core.ui_theme import section_title

def _get_meta(key: str):
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def _set_meta(key: str, value: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (key, value))
        cn.commit()

def _get_unit_counts():
    keys = [
        ("bars", ["bars_count","business_bars","num_bars"]),
        ("registers", ["registers_count","business_registers","num_registers","kassen_count"]),
        ("cloakrooms", ["cloakrooms_count","business_cloakrooms","num_cloakrooms","garderoben_count"]),
    ]
    out = {}
    for name, candidates in keys:
        val = next(( _get_meta(k) for k in candidates if _get_meta(k) not in [None,""] ), "0")
        try: out[name] = int(val)
        except: out[name] = 0
    return out

def render_cashflow(username: str, role: str, units: str):
    st.title("💰 Abrechnung")

    # ✅ Betriebsleiter / Admin darf Event setzen
    is_admin = role.lower() == "admin" or "betriebsleiter" in role.lower()

    current_event = _get_meta("current_event_name")
    event_status = _get_meta("current_event_status")  # draft / open / closed

    if is_admin:
        st.subheader("🎟️ Tages-Event festlegen")

        new_event = st.text_input("Event Name eingeben", value=current_event or "")
        col1, col2 = st.columns(2)

        if col1.button("📣 Event starten / öffnen", use_container_width=True):
            _set_meta("current_event_name", new_event)
            _set_meta("current_event_status", "open")
            st.success(f"Event '{new_event}' geöffnet!")
            st.rerun()

        if col2.button("✅ Event abschließen / sperren", use_container_width=True):
            _set_meta("current_event_status", "closed")
            st.warning(f"Event '{current_event}' abgeschlossen!")
            st.rerun()

        st.markdown("---")

    # ✅ Wenn kein Event existiert → Hinweis
    if not current_event or event_status not in ("open","draft"):
        st.info("⚠️ Kein Event/Tag vorhanden. Betriebsleiter muss zuerst ein Event starten.")
        return

    st.success(f"Aktives Event: **{current_event}**")
    st.caption("Event ist geöffnet – Barleiter können jetzt abrechnen.")

    st.markdown("---")
    section_title("📦 Einheiten")

    counts = _get_unit_counts()

    # ✅ Kacheln anzeigen
    cols = st.columns(3)
    
    if counts["bars"] > 0:
        with cols[0]:
            st.markdown(f"### 🍸 Bars\n**{counts['bars']}** Einheiten")
            if st.button("Zu den Bars", use_container_width=True):
                st.info("Bars-Abrechnung kommt im nächsten Schritt. ✅")

    if counts["registers"] > 0:
        with cols[1]:
            st.markdown(f"### 💵 Kassen\n**{counts['registers']}** Einheiten")
            if st.button("Zu den Kassen", use_container_width=True):
                st.info("Kassen-Abrechnung kommt im nächsten Schritt. ✅")

    if counts["cloakrooms"] > 0:
        with cols[2]:
            st.markdown(f"### 🧥 Garderoben\n**{counts['cloakrooms']}** Einheiten")
            if st.button("Zu den Garderoben", use_container_width=True):
                st.info("Garderoben-Abrechnung kommt im nächsten Schritt. ✅")
