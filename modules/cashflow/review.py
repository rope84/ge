# modules/cashflow/review.py
import io
import streamlit as st
from core.db import conn
from .models import get_event

def _sum_row(event_id: int, unit_type: str, field: str) -> float:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute(
            "SELECT COALESCE(SUM(value),0) FROM cashflow_item WHERE event_id=? AND unit_type=? AND field=?",
            (event_id, unit_type, field)
        ).fetchone()
    return float(r[0] or 0)

def _consolidate(event_id: int) -> dict:
    # Bars
    bar_cash   = _sum_row(event_id, "bar", "cash")
    bar_pos1   = _sum_row(event_id, "bar", "pos1")
    bar_pos2   = _sum_row(event_id, "bar", "pos2")
    bar_pos3   = _sum_row(event_id, "bar", "pos3")
    bar_vouch  = _sum_row(event_id, "bar", "voucher")
    bar_total  = bar_cash + bar_pos1 + bar_pos2 + bar_pos3 + bar_vouch

    # Kassen
    kas_cash   = _sum_row(event_id, "cash", "cash")
    kas_card   = _sum_row(event_id, "cash", "card")
    kas_total  = kas_cash + kas_card

    # Garderobe
    clo_coats  = _sum_row(event_id, "cloak", "coats_eur")
    clo_bags   = _sum_row(event_id, "cloak", "bags_eur")
    clo_total  = clo_coats + clo_bags

    return {
        "bar":  {"cash":bar_cash,"pos1":bar_pos1,"pos2":bar_pos2,"pos3":bar_pos3,"voucher":bar_vouch,"total":bar_total},
        "kas":  {"cash":kas_cash,"card":kas_card,"total":kas_total},
        "cloak":{"coats":clo_coats,"bags":clo_bags,"total":clo_total},
        "grand_total": bar_total + kas_total + clo_total
    }

def _try_build_pdf(evt, sums: dict) -> bytes | None:
    # Versuche ReportLab; falls nicht vorhanden, return None
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
    except Exception:
        return None

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    def ln(y, text, size=11, bold=False):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(2*cm, y, text)

    y = h - 2*cm
    ln(y, "A1 – Eventabrechnung", 14, True); y -= 14
    ln(y, f"Event: {evt[2]}  |  Datum: {evt[1]}  |  Status: {evt[3]}"); y -= 18

    ln(y, "Bars:", 12, True); y -= 14
    ln(y, f"Barumsatz: {sums['bar']['cash']:.2f}  | POS1: {sums['bar']['pos1']:.2f}  | POS2: {sums['bar']['pos2']:.2f}  | POS3: {sums['bar']['pos3']:.2f}  | Voucher: {sums['bar']['voucher']:.2f}")
    y -= 14
    ln(y, f"Bar gesamt: {sums['bar']['total']:.2f}", 11, True); y -= 20

    ln(y, "Kassen:", 12, True); y -= 14
    ln(y, f"Bar: {sums['kas']['cash']:.2f}  | Karte: {sums['kas']['card']:.2f}")
    y -= 14
    ln(y, f"Kassen gesamt: {sums['kas']['total']:.2f}", 11, True); y -= 20

    ln(y, "Garderobe:", 12, True); y -= 14
    ln(y, f"Jacken: {sums['cloak']['coats']:.2f}  | Taschen: {sums['cloak']['bags']:.2f}")
    y -= 14
    ln(y, f"Garderobe gesamt: {sums['cloak']['total']:.2f}", 11, True); y -= 20

    ln(y, f"Gesamtsumme: {sums['grand_total']:.2f} €", 12, True)

    c.showPage(); c.save()
    pdf = buf.getvalue()
    buf.close()
    return pdf

def render_cashflow_review(is_mgr: bool, history_only: bool=False):
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event gewählt.")
        return

    evt = get_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden.")
        return

    sums = _consolidate(ev_id)

    st.subheader("Konsolidierte Summen")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Bars gesamt", f"{sums['bar']['total']:.2f} €",
                  help=f"Bar: {sums['bar']['cash']:.2f} | POS: {sums['bar']['pos1']+sums['bar']['pos2']+sums['bar']['pos3']:.2f} | Voucher: {sums['bar']['voucher']:.2f}")
    with col2:
        st.metric("Kassen gesamt", f"{sums['kas']['total']:.2f} €",
                  help=f"Bar: {sums['kas']['cash']:.2f} | Karte: {sums['kas']['card']:.2f}")
    with col3:
        st.metric("Garderobe gesamt", f"{sums['cloak']['total']:.2f} €",
                  help=f"Jacken: {sums['cloak']['coats']:.2f} | Taschen: {sums['cloak']['bags']:.2f}")

    st.markdown(f"### Gesamtsumme: **{sums['grand_total']:.2f} €**")

    # Export
    st.markdown("---")
    pdf = _try_build_pdf(evt, sums)
    if pdf:
        st.download_button("⬇️ PDF exportieren", data=pdf, file_name="abrechnung.pdf", mime="application/pdf")
    else:
        # Fallback: einfache HTML-Datei zum "Drucken als PDF"
        html = f"""
        <html><body>
        <h2>Eventabrechnung</h2>
        <p><b>Event:</b> {evt[2]}<br><b>Datum:</b> {evt[1]}<br><b>Status:</b> {evt[3]}</p>
        <h3>Bars</h3>
        <p>Bar: {sums['bar']['cash']:.2f} | POS1: {sums['bar']['pos1']:.2f} | POS2: {sums['bar']['pos2']:.2f} | POS3: {sums['bar']['pos3']:.2f} | Voucher: {sums['bar']['voucher']:.2f}<br>
        <b>Summe:</b> {sums['bar']['total']:.2f}</p>
        <h3>Kassen</h3>
        <p>Bar: {sums['kas']['cash']:.2f} | Karte: {sums['kas']['card']:.2f}<br>
        <b>Summe:</b> {sums['kas']['total']:.2f}</p>
        <h3>Garderobe</h3>
        <p>Jacken: {sums['cloak']['coats']:.2f} | Taschen: {sums['cloak']['bags']:.2f}<br>
        <b>Summe:</b> {sums['cloak']['total']:.2f}</p>
        <h2>Gesamt: {sums['grand_total']:.2f} €</h2>
        </body></html>
        """
        st.download_button("⬇️ Export als HTML (für PDF-Druck)", data=html.encode("utf-8"),
                           file_name="abrechnung.html", mime="text/html")

    # Freigabe (nur Betriebsleiter) – optionaler Lock
    if not history_only and is_mgr:
        st.markdown("---")
        if st.button("✅ Event freigeben (abschließen)"):
            with conn() as cn:
                c = cn.cursor()
                c.execute(
                    "UPDATE events SET status='approved', approved_by=?, approved_at=datetime('now') WHERE id=?",
                    (st.session_state.get("username") or "", ev_id)
                )
                cn.commit()
            st.success("Event freigegeben.")
            st.rerun()
