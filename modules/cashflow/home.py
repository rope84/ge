# modules/cashflow/home.py
import streamlit as st
import datetime

from .models import (
    ensure_cashflow_schema, meta_caps, get_or_create_event, list_events_for_day,
    get_event, delete_event_if_open, upsert_event_units, list_active_units
)
from .utils import is_manager, allowed_unit_numbers

BADGE_OPEN = "<span style='background:#f59e0b22;color:#f59e0b;border:1px solid #f59e0b55;padding:2px 8px;border-radius:999px;font-size:11px;'>open</span>"
BADGE_DONE = "<span style='background:#22c55e22;color:#22c55e;border:1px solid #22c55e66;padding:2px 8px;border-radius:999px;font-size:11px;'>done</span>"

def _tile(label: str, subtitle: str, footer_html: str, btn_label: str, key: str) -> bool:
    with st.container(border=True):
        st.markdown(f"**{label}**  \n<span style='opacity:.8;font-size:12px'>{subtitle}</span>", unsafe_allow_html=True)
        st.markdown(footer_html, unsafe_allow_html=True)
        return st.button(btn_label, key=key, use_container_width=True)

def render_cashflow_home():
    ensure_cashflow_schema()

    user = st.session_state.get("username") or "unknown"
    role = st.session_state.get("role") or "guest"
    mgr  = is_manager(user, role)

    # --- Schritt 1: Event wählen/neu anlegen ---
    col1, col2 = st.columns([1,2])
    day = col1.date_input("Event-Datum", value=st.session_state.get("cf_day") or datetime.date.today(), key="cf_day")
    ev_opts = list_events_for_day(day)
    choose_label = "— Event auswählen —" if not ev_opts else ev_opts[0][1] + f" ({ev_opts[0][2]})"
    sel = col2.selectbox("Event auswählen", options=[("", choose_label)] + [(str(eid), f"{name} ({stt})") for eid, name, stt in ev_opts],
                         index=0, key="cf_select_event", label_visibility="visible")

    # Neuer Event (Wizard Schritt 2 – Einheiten)
    if mgr:
        with st.expander("➕ Neues Event anlegen", expanded=False):
            new_name = st.text_input("Eventname", key="cf_new_name", placeholder="z. B. OZ / Halloween")
            caps = meta_caps()
            st.caption(f"Maximal laut Betrieb: Bars={caps['bars']} | Kassen={caps['registers']} | Garderoben={caps['cloakrooms']}")
            c1,c2,c3 = st.columns(3)
            bars = c1.number_input("Bars heute", min_value=0, max_value=caps["bars"], step=1, value=min( max(1, caps["bars"]), caps["bars"] ))
            regs = c2.number_input("Kassen heute", min_value=0, max_value=caps["registers"], step=1, value=min(1, caps["registers"]))
            clo  = c3.number_input("Garderoben heute", min_value=0, max_value=caps["cloakrooms"], step=1, value=min(1, caps["cloakrooms"]))
            if st.button("Event anlegen", type="primary", use_container_width=True, disabled=(not new_name)):
                eid = get_or_create_event(day, new_name, user)
                upsert_event_units(eid, bars, regs, clo, user)
                st.session_state["cf_event_id"] = eid
                st.success("Event wurde angelegt und Einheiten fixiert.")
                st.rerun()

    # Auswahl übernehmen (existierendes Event)
    if sel and sel != "":
        st.session_state["cf_event_id"] = int(sel)

    eid = st.session_state.get("cf_event_id")
    if not eid:
        st.info("Kein Event/Tag ausgewählt.")
        return

    ev = get_event(eid)
    if not ev:
        st.warning("Event nicht gefunden – bitte erneut auswählen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status, *_ = ev
    st.markdown(
        f"**Aktives Event:** {ev_name} – {ev_day} "
        f"{BADGE_OPEN if ev_status=='open' else BADGE_DONE}",
        unsafe_allow_html=True
    )

    # Event löschen (nur wenn open)
    if mgr and ev_status == "open":
        colD,_ = st.columns([1,3])
        if colD.button("🗑️ Event löschen", help="Nur möglich solange Event nicht freigegeben ist."):
            ok = delete_event_if_open(eid)
            if ok:
                st.success("Event gelöscht.")
                st.session_state.pop("cf_event_id", None)
                st.rerun()
            else:
                st.error("Event kann nicht gelöscht werden (vermutlich bereits freigegeben).")

    st.markdown("### Einheiten")
    units = list_active_units(eid)
    if not units:
        st.info("Für dieses Event wurden noch keine Einheiten gesetzt (Betriebsleiter → Neues Event anlegen).")
        return

    # Sichtbarkeit: Manager sieht alle; andere nur ihre zugewiesenen Nummern
    allowed = allowed_unit_numbers(user)
    cols = st.columns(3)

    ci = 0
    for utype, uno, is_done in units:
        if not mgr:
            if uno not in allowed.get(utype, []):
                continue
        subtitle = {
            "bar":   "Umsatz & Voucher erfassen",
            "cash":  "Bar/Unbar (Karten) erfassen",
            "cloak": "Jacken/Taschen erfassen",
        }[utype]
        foot = BADGE_DONE if is_done else BADGE_OPEN
        with cols[ci]:
            if _tile(f"{utype.upper()} {uno}", subtitle, foot, "Bearbeiten", key=f"cf_open_{eid}_{utype}_{uno}"):
                st.session_state["cf_unit"] = (utype, uno)
                st.session_state["cf_active_tab"] = "wizard"
                st.rerun()
        ci = (ci + 1) % len(cols)
