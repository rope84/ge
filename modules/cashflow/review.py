import streamlit as st
from core.db import conn
from .utils import get_event, counts_from_meta, wardrobe_prices, set_event_status

def _sum_fields(ev_id: int, unit_type: str, fields: list[str]) -> float:
    with conn() as cn:
        c = cn.cursor()
        s = 0.0
        for f in fields:
            r = c.execute("""
                SELECT COALESCE(SUM(value),0) FROM cashflow_item
                WHERE event_id=? AND unit_type=? AND field=?
            """, (ev_id, unit_type, f)).fetchone()
            s += float(r[0] or 0.0)
        return s

def render_cashflow_review(is_mgr: bool):
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event gewählt.")
        return

    evt = get_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut wählen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status, *_ = evt
    st.markdown(f"### Review: {ev_name} – {ev_day}  ({ev_status})")

    # Summen
    bar_total    = _sum_fields(ev_id, "bar",  ["cash","pos1","pos2","pos3","voucher"])
    cash_total   = _sum_fields(ev_id, "cash", ["cash","card"])
    cloak_total  = _sum_fields(ev_id, "cloak",["coats_eur","bags_eur"])
    grand_total  = bar_total + cash_total + cloak_total

    st.metric("Bars gesamt (€)", f"{bar_total:,.2f}")
    st.metric("Kassen gesamt (€)", f"{cash_total:,.2f}")
    st.metric("Garderobe gesamt (€)", f"{cloak_total:,.2f}")
    st.subheader(f"Summe Tag: {grand_total:,.2f} €")

    st.divider()

    if is_mgr:
        c1, c2 = st.columns([1,3])
        if ev_status != "approved":
            if c1.button("✅ Tag freigeben (abschließen)", type="primary", use_container_width=True):
                set_event_status(ev_id, "approved", st.session_state.get("username") or "unknown")
                st.success("Tag freigegeben. Einträge sind für Nicht-Manager gesperrt.")
                st.rerun()
        else:
            st.info("Event ist bereits freigegeben.")

        # Platzhalter PDF
        st.caption("📄 PDF-Export (Platzhalter) – hübsches Layout folgt.")
