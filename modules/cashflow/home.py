import streamlit as st
import datetime
from typing import Dict
from .utils import (
    counts_from_meta,
    get_events_for_day,
    create_or_get_event,
    delete_event,
    get_event,
)

def _status_badge(status: str) -> str:
    col = "#10b981" if status == "approved" else "#f59e0b" if status == "open" else "#6b7280"
    return f"<span style='background:{col}22;color:{col};border:1px solid {col}66;border-radius:999px;padding:2px 8px;font-size:11px'>{status}</span>"

def render_cashflow_home(is_mgr: bool, is_bar: bool, is_kas: bool, is_clo: bool):
    # Überschrift bewusst schlank halten (Wunsch)
    # st.subheader("🏁 Übersicht")  # entfernt

    # 1) Event-Datum + Auswahl/Anlage
    c1, c2 = st.columns([1, 2])
    day = c1.date_input("Event-Datum", value=st.session_state.get("cf_day") or datetime.date.today(), key="cf_day")
    with c2:
        existing = get_events_for_day(day)
        names = [f"{e[1]} ({e[2]})" for e in existing]
        idx = 0
        if existing:
            opt = {names[i]: existing[i][0] for i in range(len(existing))}
            sel = st.selectbox("Event auswählen", names, index=0, key="cf_select_event")
            ev_id = opt[sel]
            st.session_state["cf_event_id"] = ev_id
        else:
            st.info("Kein Event an diesem Tag vorhanden.")

    if is_mgr:
        # Anlage eines zusätzlichen Events am gleichen Tag
        with st.expander("➕ Neues Event anlegen", expanded=False):
            n1, n2 = st.columns([2,1])
            new_name = n1.text_input("Eventname (neu)", key="cf_new_event_name", placeholder="z. B. OZ / Halloween")
            create_btn = n2.button("Event anlegen", type="primary", use_container_width=True, disabled=not new_name)
            if create_btn:
                ev_id = create_or_get_event(day, new_name, st.session_state.get("username") or "unknown")
                st.session_state["cf_event_id"] = ev_id
                st.success("Event angelegt und aktiv gesetzt.")
                st.rerun()

    # 2) Aktives Event anzeigen
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Bitte Event auswählen oder anlegen.")
        return

    evt = get_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut wählen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status, *_ = evt
    st.markdown(f"**Aktives Event:** {ev_name} – {ev_day} {_status_badge(ev_status)}", unsafe_allow_html=True)

    # Löschen (nur Manager)
    if is_mgr:
        del_col, _sp = st.columns([1, 5])
        if del_col.button("🗑️ Event löschen", use_container_width=True):
            delete_event(ev_id)
            st.success("Event gelöscht.")
            st.session_state.pop("cf_event_id", None)
            st.rerun()

    # 3) Einheiten-Kacheln
    cnt = counts_from_meta()
    if cnt["bars"] + cnt["registers"] + cnt["cloakrooms"] == 0:
        st.warning("Keine Einheiten konfiguriert – bitte unter Admin → Betrieb definieren.")
        return

    def _tile(lbl: str, sub: str, key: str, done: bool = False):
        badge = "<span style='font-size:11px;opacity:.7'>(offen)</span>"
        if done:
            badge = "<span style='font-size:11px;opacity:.9'>✅ gespeichert</span>"
        with st.container(border=True):
            st.markdown(f"**{lbl}**  {_status_badge('approved') if ev_status=='approved' else ''}<br>"
                        f"<span style='opacity:.75;font-size:12px'>{sub}</span><br>{badge}",
                        unsafe_allow_html=True)
            return st.button("Bearbeiten", key=key, use_container_width=True)

    st.markdown("#### Einheiten")

    # Sichtbare Typen je Rolle
    show_bar  = is_mgr or is_bar
    show_cash = is_mgr or is_kas
    show_clo  = is_mgr or is_clo

    # Bars
    if show_bar and cnt["bars"]:
        st.caption("Bars")
        cols = st.columns(min(4, max(1, cnt["bars"])))
        ci = 0
        for i in range(1, cnt["bars"] + 1):
            with cols[ci]:
                if _tile(f"Bar {i}", "Umsatz & Voucher erfassen", key=f"tile_bar_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("bar", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.session_state["cf_nav_from"] = "tile"
                    st.rerun()
            ci = (ci + 1) % len(cols)

    # Kassen
    if show_cash and cnt["registers"]:
        st.caption("Kassen")
        cols = st.columns(min(4, max(1, cnt["registers"])))
        ci = 0
        for i in range(1, cnt["registers"] + 1):
            with cols[ci]:
                if _tile(f"Kassa {i}", "Bar/Unbar (Karten) erfassen", key=f"tile_cash_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cash", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.session_state["cf_nav_from"] = "tile"
                    st.rerun()
            ci = (ci + 1) % len(cols)

    # Garderoben
    if show_clo and cnt["cloakrooms"]:
        st.caption("Garderoben")
        cols = st.columns(min(4, max(1, cnt["cloakrooms"])))
        ci = 0
        for i in range(1, cnt["cloakrooms"] + 1):
            with cols[ci]:
                if _tile(f"Garderobe {i}", "Jacken/Taschen erfassen", key=f"tile_cloak_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cloak", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.session_state["cf_nav_from"] = "tile"
                    st.rerun()
            ci = (ci + 1) % len(cols)
