# modules/cashflow/__init__.py
import streamlit as st
from .models import ensure_cashflow_schema
from .home import render_cashflow_home
from .wizard import render_cashflow_wizard
from .review import render_cashflow_review
from .utils import user_has_function

def render_cashflow():
    # Zugriff: mind. irgendeine Funktion, typischerweise Barleiter/Betriebsleiter/Kassa/Garderobe
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    # Schema sicherstellen
    ensure_cashflow_schema()

    st.markdown("### 💰 Abrechnung")

    # Rollen-basierte Tabs
    is_mgr  = user_has_function(st.session_state.get("username",""), "Betriebsleiter")
    is_bar  = user_has_function(st.session_state.get("username",""), "Barleiter")
    is_kas  = user_has_function(st.session_state.get("username",""), "Kassa")
    is_clo  = user_has_function(st.session_state.get("username",""), "Garderobe")

    # Sichtbare Tabs je nach Funktion
    tabs = []
    labels = []

    # Alle sehen die Übersicht (Kacheln) – dort greifen Filter/Assignments
    labels.append("🏁 Übersicht")
    tabs.append("home")

    # Leiter sehen ihren Wizard
    if is_bar or is_kas or is_clo or is_mgr:
        labels.append("🧭 Wizard")
        tabs.append("wizard")

    # Betriebsleiter sieht Review/Finalisierung
    if is_mgr:
        labels.append("🗂️ Review & Freigabe")
        tabs.append("review")

    st_tabs = st.tabs(labels)
    for idx, which in enumerate(tabs):
        with st_tabs[idx]:
            if which == "home":
                render_cashflow_home()
            elif which == "wizard":
                render_cashflow_wizard()
            elif which == "review":
                render_cashflow_review()
