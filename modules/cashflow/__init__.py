# modules/cashflow/__init__.py
import streamlit as st
from .models import ensure_cashflow_schema  # falls du models.py hast; sonst kannst du das Schema im home/wizard sichern
from .home import render_cashflow_home
from .wizard import render_cashflow_wizard
from .review import render_cashflow_review
from .utils import user_has_function  # falls vorhanden; sonst einfache Prüflogik in home/wizard verwenden

TAB_KEY = "cf_active_tab"  # "home" | "wizard" | "review"

def render_cashflow():
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    # Schema sicherstellen (falls du kein models.ensure hast, kann dieser Aufruf leer sein)
    try:
        ensure_cashflow_schema()
    except Exception:
        pass

    st.markdown("### 💰 Abrechnung")

    username = st.session_state.get("username", "")
    # Rollen ermitteln (Fallback: substring-check in functions)
    def _has(func_name: str) -> bool:
        try:
            return user_has_function(username, func_name)
        except Exception:
            # Fallback: ohne utils – lies functions direkt
            from core.db import conn
            with conn() as cn:
                c = cn.cursor()
                r = c.execute("SELECT functions FROM users WHERE username=?", (username,)).fetchone()
            funcs = [f.strip().lower() for f in (r[0] if r else "").split(",") if f.strip()]
            return func_name.lower() in funcs or ("admin" in funcs and func_name.lower() != "admin")

    is_mgr  = _has("Betriebsleiter") or _has("Admin")
    is_bar  = _has("Barleiter")
    is_kas  = _has("Kassa")
    is_clo  = _has("Garderobe")

    # Sichtbare Tabs
    labels, ids = [], []
    labels.append("🏁 Übersicht"); ids.append("home")
    if is_bar or is_kas or is_clo or is_mgr:
        labels.append("🧭 Wizard"); ids.append("wizard")
    if is_mgr:
        labels.append("🗂️ Review & Freigabe"); ids.append("review")

    # Aktiven Tab ermitteln/halten – und Auto-Switch wenn cf_unit gesetzt
    active = st.session_state.get(TAB_KEY) or "home"
    if st.session_state.get("cf_unit"):
        # wenn eine Einheit gewählt ist → direkt Wizard
        active = "wizard"
        st.session_state[TAB_KEY] = "wizard"

    # Tabs rendern
    st_tabs = st.tabs(labels)
    for idx, which in enumerate(ids):
        with st_tabs[idx]:
            st.session_state[TAB_KEY] = which
            if which == "home":
                render_cashflow_home(is_mgr=is_mgr, is_bar=is_bar, is_kas=is_kas, is_clo=is_clo)
            elif which == "wizard":
                render_cashflow_wizard(is_mgr=is_mgr)
            elif which == "review":
                render_cashflow_review()
