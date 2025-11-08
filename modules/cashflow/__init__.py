import streamlit as st
from .utils import user_has_function, ensure_base_schema
from .home import render_cashflow_home
from .wizard import render_cashflow_wizard
from .review import render_cashflow_review

def _reset_unit_if_fresh_entry():
    """
    Verhindert Auto-Open: Wenn wir nicht explizit vom Kachel-Klick kommen,
    wird die aktuelle Unit zurückgesetzt.
    """
    if st.session_state.get("cf_nav_from") != "tile":
        st.session_state.pop("cf_unit", None)
    st.session_state.pop("cf_nav_from", None)

def render_cashflow(*_args, **_kwargs):
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    ensure_base_schema()
    _reset_unit_if_fresh_entry()

    username = st.session_state.get("username", "")
    session_role = (st.session_state.get("role") or "").lower()

    # >>> WICHTIG: Session-Admin zählt als Manager
    is_mgr  = (
        user_has_function(username, "Betriebsleiter")
        or user_has_function(username, "Admin")
        or session_role == "admin"
    )
    is_bar  = user_has_function(username, "Barleiter")
    is_kas  = user_has_function(username, "Kassa")
    is_clo  = user_has_function(username, "Garderobe")

    # Aktiven Tab merken (optional)
    active = st.session_state.get("cf_active_tab", "home")
    labels = ["🏁 Übersicht", "🧭 Wizard"]
    keys   = ["home", "wizard"]
    if is_mgr:
        labels.append("🗂️ Review & Freigabe")
        keys.append("review")

    # Reihenfolge: wir wählen den Index anhand 'active'
    try:
        default_index = keys.index(active)
    except ValueError:
        default_index = 0

    st_tabs = st.tabs(labels)
    # Tabs zeichnen
    for i, key in enumerate(keys):
        with st_tabs[i]:
            if key == "home":
                render_cashflow_home(is_mgr=is_mgr, is_bar=is_bar, is_kas=is_kas, is_clo=is_clo)
            elif key == "wizard":
                render_cashflow_wizard(is_mgr=is_mgr, is_bar=is_bar, is_kas=is_kas, is_clo=is_clo)
            elif key == "review":
                render_cashflow_review(is_mgr=is_mgr)

    # Aktiven Tab zurückspeichern (keine harte Umschaltung nötig)
    st.session_state["cf_active_tab"] = keys[default_index]
