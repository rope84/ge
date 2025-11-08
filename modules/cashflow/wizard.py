# modules/cashflow/wizard.py
import streamlit as st
import datetime
from .models import get_event, list_active_units, mark_unit_done
from core.db import conn

BAR_FIELDS = ["cash", "pos1", "pos2", "pos3", "voucher", "tables"]
CASH_FIELDS = ["cash", "card"]
CLOAK_FIELDS = ["coats_eur", "bags_eur"]

def _load_values(eid: int, t: str, no: int):
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
           SELECT field,value FROM cashflow_item
           WHERE event_id=? AND unit_type=? AND unit_no=?
        """,(eid,t,no)).fetchall()
    out = {f:0.0 for f in (BAR_FIELDS if t=="bar" else CASH_FIELDS if t=="cash" else CLOAK_FIELDS)}
    for f,v in rows:
        try: out[f]=float(v)
        except: pass
    return out

def _save_values(eid: int, t: str, no: int, data: dict, user: str):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        for k,v in data.items():
            c.execute("""
              INSERT INTO cashflow_item(event_id,unit_type,unit_no,field,value,updated_by,updated_at)
              VALUES(?,?,?,?,?,?,?)
              ON CONFLICT(event_id,unit_type,unit_no,field)
              DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at
            """,(eid,t,no,k,float(v or 0),user,now))
        cn.commit()

def _editor(eid: int, t: str, no: int, locked: bool):
    vals = _load_values(eid,t,no)

    if t=="bar":
        c1,c2,c3,c4 = st.columns(4)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), disabled=locked)
        pos1 = c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0, value=float(vals["pos1"]), disabled=locked)
        pos2 = c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0, value=float(vals["pos2"]), disabled=locked)
        pos3 = c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0, value=float(vals["pos3"]), disabled=locked)
        v1,v2 = st.columns([2,1])
        voucher = v1.number_input("Voucher (€)", min_value=0.0, step=10.0, value=float(vals["voucher"]), disabled=locked)
        tables  = v2.number_input("Tische (Stk)", min_value=0, step=1, value=int(vals["tables"]), disabled=locked)
        total = cash+pos1+pos2+pos3+voucher
        st.info(f"Umsatz gesamt: **{total:,.2f} €**")
        return {"cash":cash,"pos1":pos1,"pos2":pos2,"pos3":pos3,"voucher":voucher,"tables":tables}

    if t=="cash":
        c1,c2 = st.columns(2)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), disabled=locked)
        card = c2.number_input("Unbar / Karte (€)", min_value=0.0, step=50.0, value=float(vals["card"]), disabled=locked)
        st.info(f"Kassa gesamt: **{cash+card:,.2f} €**")
        return {"cash":cash,"card":card}

    # cloak
    c1,c2 = st.columns(2)
    coats = c1.number_input("Jacken/Kleidung (€)", min_value=0.0, step=10.0, value=float(vals["coats_eur"]), disabled=locked)
    bags  = c2.number_input("Taschen/Rucksäcke (€)", min_value=0.0, step=10.0, value=float(vals["bags_eur"]), disabled=locked)
    st.info(f"Garderobe gesamt: **{coats+bags:,.2f} €**")
    return {"coats_eur":coats, "bags_eur":bags}

def render_cashflow_wizard():
    eid = st.session_state.get("cf_event_id")
    if not eid:
        st.info("Kein Event angelegt. Bitte Betriebsleiter startet den Tag.")
        return

    ev = get_event(eid)
    _, _, _, status, *_ = ev
    locked = (status == "approved")

    st.caption("Editor")
    sel = st.session_state.get("cf_unit")
    if not sel:
        # Falls nichts gewählt, für Manager die erste Einheit vorschlagen
        units = list_active_units(eid)
        if units:
            st.session_state["cf_unit"] = (units[0][0], units[0][1])
            sel = st.session_state["cf_unit"]
        else:
            st.info("Für dieses Event sind keine Einheiten aktiv.")
            return

    t, no = sel
    st.subheader(f"{t.upper()} {no}")

    data = _editor(eid, t, no, locked)

    colA, colB, colC = st.columns([1,1,1])
    if colA.button("⬅️ Zur Übersicht"):
        st.session_state.pop("cf_unit", None)
        st.session_state["cf_active_tab"] = "home"
        st.rerun()

    if not locked:
        if colB.button("💾 Speichern", type="primary"):
            _save_values(eid, t, no, data, st.session_state.get("username") or "unknown")
            st.success("Gespeichert.")

        done_now = colC.toggle("✔️ Abrechnung erledigt", value=False, help="Setzt den Status dieser Einheit auf erledigt.")
        if done_now:
            mark_unit_done(eid, t, no, True, st.session_state.get("username") or "unknown")
            st.session_state["cf_active_tab"] = "home"
            st.session_state.pop("cf_unit", None)
            st.rerun()
