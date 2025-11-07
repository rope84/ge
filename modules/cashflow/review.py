# modules/cashflow/review.py
import streamlit as st
from .models import get_current_event, list_units, get_entry, save_entry, close_event
from .utils import user_has_function

def _card(label: str, right: str):
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;gap:12px;
                padding:12px 14px;border-radius:12px;background:rgba(255,255,255,0.03);
                box-shadow:0 6px 16px rgba(0,0,0,0.12);">
      <div><b>{label}</b></div>
      <div style="opacity:.85">{right}</div>
    </div>
    """, unsafe_allow_html=True)

def render_cashflow_review():
    u = st.session_state.get("username","")
    if not user_has_function(u, "Betriebsleiter"):
        st.error("Nur Betriebsleiter.")
        return

    ev = get_current_event()
    if not ev:
        st.info("Kein Event.")
        return

    st.subheader(f"🗂️ Review – {ev['event_date']} · {ev['event_name']} · Status `{ev['status']}`")
    units = list_units()
    totals = 0.0
    for uinfo in units:
        entry = get_entry(ev["id"], uinfo["id"])
        t = 0.0 if not entry else float(entry.get("total",0.0))
        totals += t
        _card(uinfo["name"], f"{t:,.2f} €")
        if st.button("Öffnen", key=f"rv_open_{uinfo['id']}"):
            st.session_state["cashflow_unit_id"] = uinfo["id"]
            st.session_state["nav_choice"] = "Abrechnung"
            st.rerun()

    st.metric("GESAMT", f"{totals:,.2f} €")

    st.divider()
    if ev["status"] == "IN_PROGRESS":
        if st.button("✅ Tag final freigeben (CLOSED)", use_container_width=True):
            close_event(ev["id"])
            st.success("Freigegeben & geschlossen.")
            st.rerun()
