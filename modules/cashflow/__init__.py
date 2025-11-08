# modules/cashflow/__init__.py
import streamlit as st

# Diese drei Module müssen existieren
from .home import render_cashflow_home
from .wizard import render_cashflow_wizard
from .review import render_cashflow_review

# Optionale Utils – wenn vorhanden, verwenden wir sie
try:
    from .utils import user_has_function  # type: ignore
except Exception:
    def user_has_function(username: str, fn_name: str) -> bool:
        # Fallback: Admin sieht alles, sonst einfache Heuristik
        role = (st.session_state.get("role") or "").lower()
        if role == "admin":
            return True
        return False

def _tab_index_from_state(labels: list[str]) -> int:
    """Wähle initialen Tab anhand von st.session_state['cf_active_tab']."""
    pref = (st.session_state.get("cf_active_tab") or "").lower()
    mapping = {
        "home": 0,
        "übersicht": 0,
        "wizard": 1,
        "review": 2,
        "review & freigabe": 2,
    }
    idx = mapping.get(pref, 0)
    # falls weniger Tabs angezeigt werden, auf Bereich begrenzen
    return min(idx, max(0, len(labels) - 1))

def render_cashflow(current_user: str = "", current_role: str = "", scope: str = ""):
    """Einheitlicher Entry-Point (mit optionalen Parametern, passend zu app.py)."""
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    username = current_user or st.session_state.get("username") or ""
    # Rollen-Feststellung
    is_mgr = user_has_function(username, "Betriebsleiter") or user_has_function(username, "Admin")
    is_bar = user_has_function(username, "Barleiter")
    is_kas = user_has_function(username, "Kassa")
    is_clo = user_has_function(username, "Garderobe")

    st.markdown("### 💰 Abrechnung")

    # Sichtbare Tabs je nach Funktion
    labels: list[str] = ["🏁 Übersicht", "🧭 Wizard"]
    show_review = bool(is_mgr)
    if show_review:
        labels.append("🗂️ Review & Freigabe")

    # Initialen Tab anhand State wählen
    initial_index = _tab_index_from_state(labels)
    st_tabs = st.tabs(labels)

    # Übersicht
    with st_tabs[0]:
        render_cashflow_home(
            is_mgr=is_mgr,
            is_bar=is_bar,
            is_kas=is_kas,
            is_clo=is_clo,
        )

    # Wizard
    with st_tabs[1]:
        render_cashflow_wizard()

    # Review & Freigabe (nur Manager)
    if show_review:
        with st_tabs[2]:
            render_cashflow_review()
