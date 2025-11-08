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
    # Login prüfen
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    # Basis-Schema sicherstellen (events, items etc.)
    ensure_base_schema()

    # Beim Einstieg Unit-Editor nicht automatisch öffnen
    _reset_unit_if_fresh_entry()

    username = st.session_state.get("username", "")
    is_mgr  = user_has_function(username, "Betriebsleiter") or user_has_function(username, "Admin")
    is_bar  = user_has_function(username, "Barleiter")
    is_kas  = user_has_function(username, "Kassa")
    is_clo  = user_has_function(username, "Garderobe")

    # Tabs
    labels = ["🏁 Übersicht", "🧭 Wizard"]
    keys   = ["home", "wizard"]
    if is_mgr:
        labels.append("🗂️ Review & Freigabe")
        keys.append("review")

    st_tabs = st.tabs(labels)
    for i, key in enumerate(keys):
        with st_tabs[i]:
            if key == "home":
                render_cashflow_home(is_mgr=is_mgr, is_bar=is_bar, is_kas=is_kas, is_clo=is_clo)
            elif key == "wizard":
                render_cashflow_wizard(is_mgr=is_mgr, is_bar=is_bar, is_kas=is_kas, is_clo=is_clo)
            elif key == "review":
                render_cashflow_review(is_mgr=is_mgr)
