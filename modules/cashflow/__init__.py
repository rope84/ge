# modules/cashflow/__init__.py
import streamlit as st
from .models import ensure_cashflow_schema
from .utils import user_has_function
from .home import (
    render_event_admin,
    render_overview_kacheln,
)
from .wizard import render_cashflow_wizard
from .review import render_cashflow_review

VIEW_KEY = "cf_view"  # "event" | "overview" | "capture" | "review" | "history" (für Barleiter)

def _init_view(default_view: str):
    if VIEW_KEY not in st.session_state:
        st.session_state[VIEW_KEY] = default_view

def _switch(view: str):
    st.session_state[VIEW_KEY] = view
    st.rerun()

def render_cashflow(*_args, **_kwargs):
    if not st.session_state.get("auth"):
        st.error("Bitte einloggen.")
        return

    ensure_cashflow_schema()

    username = st.session_state.get("username", "")
    is_mgr  = user_has_function(username, "Betriebsleiter") or user_has_function(username, "Admin")
    is_bar  = user_has_function(username, "Barleiter")
    is_kas  = user_has_function(username, "Kassa")
    is_clo  = user_has_function(username, "Garderobe")

    # Default-View festlegen
    _init_view("event" if is_mgr else "overview")

    # Kopf
    st.title("💰 Abrechnung")

    # View-Auswahl (radiogesteuert, programmatisch änderbar)
    if is_mgr:
        choice = st.radio(
            "Schritt wählen", 
            ["Event", "Einheiten & Kacheln", "Erfassen", "Review"],
            index=["event","overview","capture","review"].index(st.session_state[VIEW_KEY]),
            horizontal=True,
            key="cf_view_radio",
        )
        # Map zurück in session_state
        mapping = {"Event":"event","Einheiten & Kacheln":"overview","Erfassen":"capture","Review":"review"}
        if mapping.get(choice) != st.session_state[VIEW_KEY]:
            st.session_state[VIEW_KEY] = mapping[choice]
    else:
        choice = st.radio(
            "Ansicht", 
            ["Erfassen", "Rückblick"],
            index=["capture","history"].index(st.session_state[VIEW_KEY] if st.session_state[VIEW_KEY] in ("capture","history") else "capture"),
            horizontal=True,
            key="cf_view_radio_user",
        )
        mapping = {"Erfassen":"capture", "Rückblick":"history"}
        if mapping.get(choice) != st.session_state[VIEW_KEY]:
            st.session_state[VIEW_KEY] = mapping[choice]

    # Render nach View
    view = st.session_state[VIEW_KEY]

    if view == "event":
        # Betriebsleiter: Event anlegen/auswählen/löschen + per-Event Einheiten (mit Deckelung)
        next_clicked = render_event_admin()
        if next_clicked:
            _switch("overview")

    elif view == "overview":
        # Kacheln + Status; Kachel-Klick setzt cf_unit und schaltet auf "capture"
        opened = render_overview_kacheln(is_mgr=is_mgr, is_bar=is_bar, is_kas=is_kas, is_clo=is_clo)
        if opened:
            _switch("capture")

    elif view == "capture":
        # Editor für die ausgewählte Einheit (Bar/Kassa/Garderobe)
        back_pressed = render_cashflow_wizard()
        if back_pressed:
            _switch("overview")

    elif view == "review":
        # Konsolidierte Ansicht + Freigabe + Export
        render_cashflow_review(is_mgr=is_mgr)

    elif view == "history":
        # Optional: kann im Review-Modul eine einfache Verlaufsliste/Lesesicht anbieten
        render_cashflow_review(is_mgr=False, history_only=True)

    else:
        st.info("Bitte oben eine Ansicht wählen.")
