# modules/cashflow/home.py
import streamlit as st
import datetime
from .models import (
    list_events_for_day, get_event, get_or_create_event,
    save_event_counts, delete_event, unit_has_entries
)
from .utils import global_unit_caps

def _cap(value: int, cap: int) -> int:
    try:
        v = int(value)
    except Exception:
        v = 0
    return max(0, min(v, int(cap)))

def render_event_admin() -> bool:
    """Schritt: Event anlegen/auswählen/löschen + pro-Event Einheiten (gedeckelt).
    Rückgabewert: True, wenn 'Weiter' geklickt wurde.
    """
    # Header-Felder
    default_day = st.session_state.get("cf_event_day") or datetime.date.today()
    default_name = st.session_state.get("cf_event_name") or ""
    col1, col2 = st.columns([1, 2])
    day = col1.date_input("Event-Datum", value=default_day, key="cf_day")
    name = col2.text_input("Eventname", value=default_name, key="cf_name", placeholder="z. B. OZ / Halloween")

    topA, topB = st.columns([1, 3])
    if topA.button("▶️ Event öffnen/fortsetzen", type="primary", use_container_width=True, disabled=(not name or not day)):
        ev_id = get_or_create_event(day.isoformat(), name, st.session_state.get("username") or "unknown")
        st.session_state["cf_event_id"]   = ev_id
        st.session_state["cf_event_day"]  = day
        st.session_state["cf_event_name"] = name
        st.success("Event aktiv.")
        st.rerun()

    # Events an diesem Tag
    rows = list_events_for_day(day.isoformat())
    if not rows:
        st.info("Für dieses Datum gibt es noch keine Events.")
        return False

    # Auswahl vorhandener Events
    labels = [f"{nm}  •  ({stt})" for (_id, nm, stt, *_r) in rows]
    current = st.session_state.get("cf_event_id")
    try:
        idx = next((i for i,(eid,*_) in enumerate(rows) if eid == current), 0)
    except Exception:
        idx = 0
    sel_idx = st.selectbox("Event auswählen", range(len(rows)), format_func=lambda i: labels[i], index=idx)
    ev_id, ev_name, ev_status, ev_bars, ev_regs, ev_clo = rows[sel_idx]

    # Aktivieren & Löschen
    cA, cB, cC = st.columns([1,1,2])
    if cA.button("Aktivieren", use_container_width=True):
        st.session_state["cf_event_id"]   = ev_id
        st.session_state["cf_event_day"]  = day
        st.session_state["cf_event_name"] = ev_name
        st.success("Event aktiviert.")
        st.rerun()

    with cB:
        st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
        confirm = st.checkbox("Löschen bestätigen", key="cf_del_confirm")
        if st.button("🗑️ Event löschen", use_container_width=True, disabled=not confirm):
            delete_event(ev_id)
            if st.session_state.get("cf_event_id") == ev_id:
                st.session_state.pop("cf_event_id", None)
            st.success("Event gelöscht.")
            st.rerun()

    # Aktives Event laden (falls vorhanden)
    active_id = st.session_state.get("cf_event_id")
    if not active_id:
        st.info("Kein aktives Event gewählt.")
        return False

    evt = get_event(active_id)
    if not evt:
        st.warning("Aktives Event nicht gefunden.")
        st.session_state.pop("cf_event_id", None)
        return False

    _, ev_day, ev_name, ev_status, bars_open, regs_open, clo_open = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    # Per-Event Einheiten – mit Deckelung auf Admin-Maxe
    caps = global_unit_caps()
    st.markdown("#### Einheiten für diesen Tag")
    e1, e2, e3, e4 = st.columns([1,1,1,1])
    bars_val = _cap(bars_open if bars_open is not None else caps["bars"], caps["bars"])
    regs_val = _cap(regs_open if regs_open is not None else caps["registers"], caps["registers"])
    clo_val  = _cap(clo_open  if clo_open  is not None else caps["cloakrooms"], caps["cloakrooms"])

    bars = e1.number_input("Bars aktiv", min_value=0, max_value=int(caps["bars"]), step=1, value=int(bars_val), key="cfg_bars_open")
    regs = e2.number_input("Kassen aktiv", min_value=0, max_value=int(caps["registers"]), step=1, value=int(regs_val), key="cfg_regs_open")
    clo  = e3.number_input("Garderoben aktiv", min_value=0, max_value=int(caps["cloakrooms"]), step=1, value=int(clo_val), key="cfg_clo_open")

    if e4.button("💾 Speichern", use_container_width=True, key="btn_save_event_counts"):
        save_event_counts(active_id, bars, regs, clo)
        st.success("Einheiten gespeichert.")
        st.rerun()

    st.markdown("---")
    next_clicked = st.button("Weiter ➜ Einheiten & Kacheln", type="primary", use_container_width=True)
    return bool(next_clicked)

def _tile(label: str, subtitle: str, status_icon: str, key: str) -> bool:
    with st.container(border=True):
        st.markdown(
            f"**{label}** {status_icon}  \n"
            f"<span style='opacity:.7;font-size:12px'>{subtitle}</span>",
            unsafe_allow_html=True
        )
        return st.button("Bearbeiten", key=key, use_container_width=True)

def render_overview_kacheln(is_mgr: bool, is_bar: bool, is_kas: bool, is_clo: bool) -> bool:
    """Zeigt Kacheln gemäß aktivem Event. Rückgabe True, wenn eine Kachel geöffnet wurde."""
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event/Tag vorhanden. (Betriebsleiter: Schritt 'Event' zuerst abschließen.)")
        return False

    evt = get_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte unter 'Event' neu aktivieren.")
        st.session_state.pop("cf_event_id", None)
        return False

    _, ev_day, ev_name, ev_status, bars_open, regs_open, clo_open = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    caps = global_unit_caps()
    bars = _cap(bars_open if bars_open is not None else caps["bars"], caps["bars"])
    regs = _cap(regs_open if regs_open is not None else caps["registers"], caps["registers"])
    clo  = _cap(clo_open  if clo_open  is not None else caps["cloakrooms"], caps["cloakrooms"])

    opened = False

    # Bars
    if (is_mgr or is_bar) and bars > 0:
        st.caption("Bars")
        cols = st.columns(min(4, bars))
        ci = 0
        for i in range(1, bars+1):
            done = unit_has_entries(ev_id, "bar", i)
            icon = "✅" if done else "⏳"
            with cols[ci]:
                if _tile(f"Bar {i}", "Umsatz & Voucher erfassen", icon, key=f"cf_open_bar_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("bar", i)
                    opened = True
            ci = (ci + 1) % len(cols)

    # Kassen
    if (is_mgr or is_kas) and regs > 0:
        st.caption("Kassen")
        cols = st.columns(min(4, regs))
        ci = 0
        for i in range(1, regs+1):
            done = unit_has_entries(ev_id, "cash", i)
            icon = "✅" if done else "⏳"
            with cols[ci]:
                if _tile(f"Kassa {i}", "Bar/Unbar (Karten) erfassen", icon, key=f"cf_open_cash_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cash", i)
                    opened = True
            ci = (ci + 1) % len(cols)

    # Garderoben
    if (is_mgr or is_clo) and clo > 0:
        st.caption("Garderoben")
        cols = st.columns(min(4, clo))
        ci = 0
        for i in range(1, clo+1):
            done = unit_has_entries(ev_id, "cloak", i)
            icon = "✅" if done else "⏳"
            with cols[ci]:
                if _tile(f"Garderobe {i}", "Jacken/Taschen erfassen", icon, key=f"cf_open_cloak_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cloak", i)
                    opened = True
            ci = (ci + 1) % len(cols)

    return opened
