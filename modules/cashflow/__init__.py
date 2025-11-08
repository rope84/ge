import streamlit as st
from .models import ensure_cashflow_schema
from .home import render_cashflow_home
from .wizard import render_cashflow_wizard
from .review import render_cashflow_review
from .utils import user_has_function

def render_cashflow():
    # Login erforderlich
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    # DB-Schema sicherstellen
    ensure_cashflow_schema()

    st.markdown("### 💰 Abrechnung")

    username = st.session_state.get("username", "") or ""
    # Rollen prüfen (Admin wird in user_has_function() automatisch als True gewertet)
    is_mgr = user_has_function(username, "Betriebsleiter")
    is_bar = user_has_function(username, "Barleiter")
    is_kas = user_has_function(username, "Kassa")
    is_clo = user_has_function(username, "Garderobe")

    # Tabs zusammenstellen
    labels, keys = [], []

    labels.append("🏁 Übersicht"); keys.append("home")
    if is_mgr or is_bar or is_kas or is_clo:
        labels.append("🧭 Wizard"); keys.append("wizard")
    if is_mgr:
        labels.append("🗂️ Review & Freigabe"); keys.append("review")

    # Aktiven Tab aus Session
    active_key = st.session_state.get("cf_active_tab") or "home"
    try:
        active_idx = keys.index(active_key)
    except ValueError:
        active_idx = 0

    st_tabs = st.tabs(labels)

    for idx, which in enumerate(keys):
        with st_tabs[idx]:
            if which == "home":
                # WICHTIG: Flags durchreichen
                render_cashflow_home(is_mgr=is_mgr, is_bar=is_bar, is_kas=is_kas, is_clo=is_clo)
            elif which == "wizard":
                render_cashflow_wizard()
            elif which == "review":
                render_cashflow_review()

    # Wenn der Wizard aus Home angewählt wurde, im nächsten Render direkt dorthin springen
    if st.session_state.get("cf_active_tab") == "wizard" and active_key != "wizard":
        st.experimental_rerun()
