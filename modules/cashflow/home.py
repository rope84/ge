# modules/cashflow/home.py
import streamlit as st
from datetime import date
from .models import ensure_cashflow_schema, get_current_event, create_event, open_event, close_event, list_units, upsert_unit
from .utils import user_has_function, numbers_from_meta, nice_unit_name

def _tile(label: str, sub: str):
    st.markdown(f"""
    <div style="padding:14px;border-radius:14px;background:rgba(255,255,255,0.03);
                box-shadow:0 6px 16px rgba(0,0,0,0.15);">
      <div style="font-weight:600">{label}</div>
      <div style="opacity:.8;font-size:13px">{sub}</div>
    </div>
    """, unsafe_allow_html=True)

def _sync_units_from_meta():
    nums = numbers_from_meta()
    # Bars
    for i in range(1, nums["bars"]+1):
        upsert_unit("bar", i, nice_unit_name("bar", i))
    # Kassen
    for i in range(1, nums["kassen"]+1):
        upsert_unit("kassa", i, nice_unit_name("kassa", i))
    # Garderobe
    for i in range(1, nums["cloak"]+1):
        upsert_unit("cloak", i, nice_unit_name("cloak", i))

def render_cashflow_home():
    ensure_cashflow_schema()
    is_mgr = user_has_function(st.session_state.get("username",""), "Betriebsleiter")

    ev = get_current_event()

    cols = st.columns(2)
    with cols[0]:
        if ev:
            st.markdown(f"**Aktueller Tag:** {ev['event_date']} · *{ev['event_name']}* · Status: `{ev['status']}`")
        else:
            st.info("Kein Event/Tag vorhanden.")

    with cols[1]:
        if is_mgr:
            with st.popover("🔧 Tagessteuerung"):
                d = st.date_input("Datum", value=date.today())
                name = st.text_input("Event-Name", placeholder="z.B. OZ / Halloween")
                c1, c2, c3 = st.columns(3)
                if c1.button("➕ Anlegen"):
                    new_id = create_event(str(d), name or "Event", st.session_state.get("username",""))
                    st.success(f"Event #{new_id} angelegt (DRAFT).")
                    st.rerun()
                if ev and ev["status"] in ("DRAFT", "OPEN"):
                    if c2.button("▶️ Start (IN_PROGRESS)"):
                        open_event(ev["id"])
                        st.success("Tag gestartet.")
                        st.rerun()
                if ev and ev["status"] in ("IN_PROGRESS",):
                    if c3.button("✅ Schließen (CLOSED)"):
                        close_event(ev["id"])
                        st.success("Tag geschlossen.")
                        st.rerun()

    st.divider()

    # Units aus meta同步isieren (falls Anzahl geändert)
    _sync_units_from_meta()
    units = list_units()
    if not units:
        st.info("Keine Einheiten (Bars/Kassen/Garderobe) konfiguriert – bitte im Admin-Bereich (Betrieb) Anzahl hinterlegen.")
        return

    # Kacheln
    st.markdown("#### Einheiten")
    grid = st.columns(3)
    for i, u in enumerate(units):
        with grid[i % 3]:
            _tile(f"{u['name']}", f"Typ: {u['unit_type'].capitalize()}")
            if st.button("Öffnen", key=f"open_unit_{u['id']}", use_container_width=True, disabled=not ev or ev["status"] not in ("IN_PROGRESS","DRAFT","OPEN")):
                # Wizard mit ausgewählter Unit öffnen
                st.session_state["cashflow_unit_id"] = u["id"]
                st.session_state["nav_choice"] = "Abrechnung"  # bleibt gleich
                st.rerun()
