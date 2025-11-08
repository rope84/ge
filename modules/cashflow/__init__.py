# modules/cashflow/__init__.py
import streamlit as st
from .models import ensure_cashflow_schema
from .home import render_cashflow_home
from .wizard import render_cashflow_wizard
from .review import render_cashflow_review
from .utils import user_has_function, is_manager

def render_cashflow():
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    ensure_cashflow_schema()

    user = st.session_state.get("username") or ""
    role = st.session_state.get("role") or ""

    mgr  = is_manager(user, role)
    is_bar = user_has_function(user, "Barleiter")
    is_kas = user_has_function(user, "Kassa")
    is_clo = user_has_function(user, "Garderobe")

    labels = ["🏁 Übersicht", "🧭 Wizard"]
    pages  = ["home",       "wizard"]
    if mgr:
        labels.append("🗂️ Review & Freigabe")
        pages.append("review")

    active = st.session_state.get("cf_active_tab") or "home"
    try:
        idx = pages.index(active)
    except ValueError:
        idx = 0

    ts = st.tabs(labels)
    for i, p in enumerate(pages):
        with ts[i]:
            if p == "home":
                render_cashflow_home()
            elif p == "wizard":
                render_cashflow_wizard()
            elif p == "review":
                render_cashflow_review()
    # Reset gewünschte Start-Tab-Logik
    st.session_state["cf_active_tab"] = pages[idx]
