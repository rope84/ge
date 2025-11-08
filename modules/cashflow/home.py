import streamlit as st
import datetime
from typing import Optional, Tuple

from .models import (
    ensure_cashflow_schema,
    create_or_get_event,
    event_info,
    counts_for_event,
    get_global_caps,
    upsert_event_config,
    unit_total,
    unit_done,
    delete_event,
)

def _list_events_for_day(day_iso: str):
    from core.db import conn
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, name, status FROM events WHERE event_date=? ORDER BY created_at DESC",
            (day_iso,),
        ).fetchall()

def render_cashflow_home():
    ensure_cashflow_schema()
    st.subheader("")  # Überschrift bewusst leer, wie gewünscht

    user = st.session_state.get("username") or "unknown"
    role = (st.session_state.get("role") or "").lower()
    funcs = (st.session_state.get("functions") or "").lower()
    is_mgr = (role == "admin") or ("admin" in funcs) or ("betriebsleiter" in funcs)
    is_bar = ("barleiter" in funcs)
    is_kas = ("kassa" in funcs)
    is_clo = ("garderobe" in funcs)

    # --- 1) Event anlegen/öffnen ---
    c1, c2 = st.columns([1, 2])
    day = c1.date_input("Event-Datum", value=st.session_state.get("cf_day") or datetime.date.today(), key="cf_day")
    name = c2.text_input("Eventname", value=st.session_state.get("cf_name") or "", key="cf_name", placeholder="z. B. OZ / Halloween")

    # Events des Tages
    options = _list_events_for_day(day.isoformat())
    if options:
        nice = [f"{e[0]} – {e[1]} ({e[2]})" for e in options]
        ev_select = st.selectbox("Event wählen", list(zip([o[0] for o in options], nice)),
                                 format_func=lambda x: x[1] if isinstance(x, tuple) else x,
                                 key="cf_event_select")
    else:
        ev_select = None

    cols = st.columns(3)
    if is_mgr:
        if cols[0].button("▶️ Event öffnen/fortsetzen", type="primary", use_container_width=True, disabled=(not name or not day)):
            ev_id = create_or_get_event(day, name, user)
            st.session_state["cf_event_id"] = ev_id
            st.session_state.pop("cf_unit", None)
            st.success("Event aktiv.")
            st.rerun()

        if ev_select and cols[1].button("Öffnen (Auswahl)", use_container_width=True):
            st.session_state["cf_event_id"] = int(ev_select[0] if isinstance(ev_select, tuple) else ev_select)
            st.session_state.pop("cf_unit", None)
            st.rerun()

        # Optional: Event löschen (Safety)
        if ev_select and cols[2].button("🗑️ Event löschen", use_container_width=True):
            delete_event(int(ev_select[0] if isinstance(ev_select, tuple) else ev_select), user)
            st.success("Event gelöscht.")
            if st.session_state.get("cf_event_id") == (ev_select[0] if isinstance(ev_select, tuple) else ev_select):
                st.session_state.pop("cf_event_id", None)
                st.session_state.pop("cf_unit", None)
            st.rerun()
    else:
        st.caption("Event wird vom Betriebsleiter freigegeben. Danach kannst du deine Einheit bearbeiten.")

    # Aktives Event?
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        # Barleiter sehen Rückblick (bleibt unverändert)
        if not is_mgr:
            st.info("Kein aktives Event. Bitte auf Freigabe warten.")
        else:
            st.info("Kein Event/Tag aktiv.")
        return

    # --- 2) Header Info ---
    evt = event_info(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut öffnen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    # Wenn abgeschlossen & kein Manager → zurück
    if (ev_status == "approved") and (not is_mgr):
        st.info("Dieses Event ist abgeschlossen.")
        st.session_state.pop("cf_event_id", None)
        st.session_state.pop("cf_unit", None)
        st.rerun()
        return

    # --- 3) NEU: Event-Konfiguration (Anzahl Einheiten) ---
    # Sichtbar nur für Manager/Admin; mit Kappung auf Admin-Grenzen
    if is_mgr:
        caps = get_global_caps()
        current = counts_for_event(ev_id)

        with st.expander("⚙️ Event-Konfiguration (geöffnete Einheiten)", expanded=True):
            cc1, cc2, cc3 = st.columns(3)
            bars = cc1.number_input("Bars geöffnet", min_value=0, max_value=int(caps["bars"]),
                                    value=int(current["bars"]), step=1, key=f"cfg_bars_{ev_id}")
            regs = cc2.number_input("Kassen geöffnet", min_value=0, max_value=int(caps["registers"]),
                                    value=int(current["registers"]), step=1, key=f"cfg_regs_{ev_id}")
            clo  = cc3.number_input("Garderoben geöffnet", min_value=0, max_value=int(caps["cloakrooms"]),
                                    value=int(current["cloakrooms"]), step=1, key=f"cfg_clo_{ev_id}")

            csave, creset = st.columns([1,1])
            if csave.button("💾 Konfiguration speichern", type="primary", use_container_width=True, key=f"cfg_save_{ev_id}"):
                upsert_event_config(ev_id, bars, regs, clo, user)
                st.success("Event-Konfiguration gespeichert.")
                st.rerun()
            if creset.button("↺ Auf Admin-Obergrenzen setzen", use_container_width=True, key=f"cfg_reset_{ev_id}"):
                upsert_event_config(ev_id, caps["bars"], caps["registers"], caps["cloakrooms"], user)
                st.success("Auf Obergrenzen gesetzt.")
                st.rerun()

    # --- 4) Kacheln nach aktueller Event-Konfig ---
    cfg = counts_for_event(ev_id)

    def _tile(label: str, subtitle: str, key: str, disabled: bool=False) -> bool:
        with st.container(border=True):
            st.markdown(f"**{label}**  \n<span style='opacity:.7;font-size:12px'>{subtitle}</span>", unsafe_allow_html=True)
            return st.button("Bearbeiten" if not disabled else "Ansehen", key=key, use_container_width=True, disabled=disabled)

    def _render_group(title: str, unit_type: str, count: int, allowed: bool):
        if not count or not allowed:
            return
        st.caption(title)
        cols = st.columns(min(4, max(1, count)))
        ci = 0
        for i in range(1, count+1):
            total = unit_total(ev_id, unit_type, i)
            done  = unit_done(ev_id, unit_type, i)
            base_title = f"{title[:-1]} {i}"
            label = f"{base_title} – {total:,.2f} €" if total > 0 else base_title
            subtitle = "✔ erledigt" if done else "⏳ offen"
            readonly = (ev_status == "approved") and (not is_mgr)
            with cols[ci]:
                if _tile(label, subtitle, key=f"cf_open_{unit_type}_{ev_id}_{i}", disabled=readonly and not is_mgr):
                    st.session_state["cf_unit"] = (unit_type, i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)

    _render_group("Bars",       "bar",   int(cfg["bars"]),       allowed=(is_mgr or is_bar))
    _render_group("Kassen",     "cash",  int(cfg["registers"]),  allowed=(is_mgr or is_kas))
    _render_group("Garderoben", "cloak", int(cfg["cloakrooms"]), allowed=(is_mgr or is_clo))
