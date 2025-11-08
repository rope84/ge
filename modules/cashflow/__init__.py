# modules/cashflow/__init__.py
import streamlit as st
from .models import ensure_cashflow_schema
from .home import render_cashflow_home
from .wizard import render_cashflow_wizard
from .review import render_cashflow_review
from .utils import user_has_function

def _is_manager(username: str) -> bool:
    """Betriebsleiter-Logik inkl. Admin-Fallback & Session-Role."""
    # DB-Funktionen
    if user_has_function(username, "Betriebsleiter"):
        return True
    if user_has_function(username, "Admin"):  # Admin zählt als Manager
        return True
    # Session-Rolle (Fallback, falls functions-Feld leer ist)
    return (st.session_state.get("role", "").lower() == "admin")

def _is_bar(username: str) -> bool:
    return user_has_function(username, "Barleiter")

def _is_cash(username: str) -> bool:
    # Benenne hier so, wie deine Function wirklich heißt (z.B. "Kassa" oder "Kassier")
    return user_has_function(username, "Kassa") or user_has_function(username, "Kassier")

def _is_cloak(username: str) -> bool:
    return user_has_function(username, "Garderobe")

def render_cashflow(*_args, **_kwargs):
    """
    Tolerante Signatur (nimmt beliebige Args), damit sie mit app.py kompatibel ist,
    egal ob render_cashflow(), render_cashflow(user, role) oder (user, role, scope) aufgerufen wird.
    """
    # Zugriff nur wenn eingeloggt
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    # Schema sicherstellen (events, cashflow_item, audit, ...)
    ensure_cashflow_schema()

    st.markdown("### 💰 Abrechnung")

    username = st.session_state.get("username", "") or ""
    is_mgr  = _is_manager(username)
    is_bar  = _is_bar(username)
    is_kas  = _is_cash(username)
    is_clo  = _is_cloak(username)

    # Tabs zusammenstellen
    labels = []
    which  = []

    # Übersicht sehen alle – hier stehen die Kacheln (Bars/Kassen/Garderobe)
    labels.append("🏁 Übersicht")
    which.append("home")

    # Wizard für alle operativen Rollen ODER Manager
    if is_mgr or is_bar or is_kas or is_clo:
        labels.append("🧭 Wizard")
        which.append("wizard")

    # Review & Freigabe nur für Manager/Betriebsleiter/Admin
    if is_mgr:
        labels.append("🗂️ Review & Freigabe")
        which.append("review")

    # Falls jemand gar keine passende Funktion hat, wenigstens die Übersicht und Hinweis zeigen
    if len(labels) == 1:  # nur Übersicht
        st.info("Du hast aktuell keine Abrechnungs-Funktion zugewiesen. Bitte Admin/Betriebsleiter kontaktieren.")

    st_tabs = st.tabs(labels)
    for i, w in enumerate(which):
        with st_tabs[i]:
            if w == "home":
                render_cashflow_home()
            elif w == "wizard":
                render_cashflow_wizard()
            elif w == "review":
                render_cashflow_review()
