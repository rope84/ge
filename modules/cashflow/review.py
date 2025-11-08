# modules/cashflow/review.py
import io
import streamlit as st
import pandas as pd
from core.db import conn
from .models import get_event, approve_event, list_active_units

def _aggregates(eid: int) -> pd.DataFrame:
    with conn() as cn:
        df = pd.read_sql("""
           SELECT unit_type, unit_no, field, value
           FROM cashflow_item
           WHERE event_id=?
        """, cn, params=(eid,))
    if df.empty:
        return pd.DataFrame(columns=["Kategorie","Summe (€)"])
    def cat(row):
        if row["unit_type"]=="bar":
            return {"cash":"Bar","pos1":"Karte","pos2":"Karte","pos3":"Karte","voucher":"Voucher","tables":"Tische"}.get(row["field"], "Sonstiges")
        if row["unit_type"]=="cash":
            return {"cash":"Bar","card":"Karte"}.get(row["field"], "Sonstiges")
        return {"coats_eur":"Garderobe","bags_eur":"Garderobe"}.get(row["field"], "Sonstiges")
    df["Kategorie"] = df.apply(cat, axis=1)
    agg = df.groupby("Kategorie", as_index=False)["value"].sum().rename(columns={"value":"Summe (€)"})
    return agg

def _export_pdf(df: pd.DataFrame, ev_label: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        w, h = A4
        y = h - 20*mm
        c.setFont("Helvetica-Bold", 14)
        c.drawString(20*mm, y, f"Abrechnung – {ev_label}")
        y -= 12*mm
        c.setFont("Helvetica", 11)
        for _,r in df.iterrows():
            c.drawString(20*mm, y, f"{r['Kategorie']}: {r['Summe (€)']:.2f} €")
            y -= 8*mm
            if y < 20*mm:
                c.showPage(); y = h - 20*mm; c.setFont("Helvetica", 11)
        c.showPage(); c.save()
        return buf.getvalue()
    except Exception:
        return df.to_csv(index=False).encode("utf-8")

def render_cashflow_review():
    eid = st.session_state.get("cf_event_id")
    if not eid:
        st.info("Kein Event.")
        return

    ev = get_event(eid)
    if not ev:
        st.info("Event nicht gefunden.")
        return

    _, ev_day, ev_name, status, *_ = ev
    st.subheader("Review & Freigabe")
    st.caption(f"{ev_name} – {ev_day} – Status: {status}")

    # Übersicht Einheitenstatus
    units = list_active_units(eid)
    if units:
        st.write("**Einheitenstatus:** " + ", ".join([f"{t.upper()} {n} ({'done' if d else 'open'})" for t,n,d in units]))
    else:
        st.write("Keine aktiven Einheiten gesetzt.")

    df = _aggregates(eid)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Export
    blob = _export_pdf(df, f"{ev_name} – {ev_day}")
    st.download_button("📄 PDF/CSV exportieren", data=blob,
                       file_name=f"Abrechnung_{ev_day}_{ev_name}.pdf", mime="application/pdf")

    # Freigabe
    if status != "approved":
        if st.button("✅ Tag freigeben (abschließen)", type="primary"):
            approve_event(eid, st.session_state.get("username") or "unknown")
            st.success("Event freigegeben.")
            st.rerun()
    else:
        st.info("Event ist bereits freigegeben.")
