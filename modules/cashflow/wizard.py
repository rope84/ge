# modules/cashflow/wizard.py
import streamlit as st
from .models import get_current_event, get_entry, save_entry
from .utils import user_has_function
from core.db import conn

def _bar_form(data: dict) -> tuple[dict, float]:
    c1,c2,c3,c4 = st.columns(4)
    data["cash"] = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(data.get("cash",0.0)))
    data["pos1"] = c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0, value=float(data.get("pos1",0.0)))
    data["pos2"] = c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0, value=float(data.get("pos2",0.0)))
    data["pos3"] = c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0, value=float(data.get("pos3",0.0)))
    r2c1, r2c2 = st.columns([2,1])
    data["voucher"] = r2c1.number_input("Voucher (€)", min_value=0.0, step=10.0, value=float(data.get("voucher",0.0)))
    data["tables"]  = int(r2c2.number_input("Tische (Stk)", min_value=0, step=1, value=int(data.get("tables",0))))
    total = float(data["cash"])+float(data["pos1"])+float(data["pos2"])+float(data["pos3"])+float(data["voucher"])
    st.metric("Umsatz gesamt", f"{total:,.2f} €")
    return data, total

def _kassa_form(data: dict) -> tuple[dict,float]:
    c1,c2 = st.columns(2)
    data["cash"] = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(data.get("cash",0.0)))
    data["card"] = c2.number_input("Unbar / Bankomat (€)", min_value=0.0, step=50.0, value=float(data.get("card",0.0)))
    total = float(data["cash"])+float(data["card"])
    st.metric("Umsatz gesamt", f"{total:,.2f} €")
    return data, total

def _cloak_form(data: dict) -> tuple[dict,float]:
    c1,c2 = st.columns(2)
    data["coats_eur"] = c1.number_input("Jacken/Kleidung (€)", min_value=0.0, step=10.0, value=float(data.get("coats_eur",0.0)))
    data["bags_eur"]  = c2.number_input("Taschen/Rucksäcke (€)", min_value=0.0, step=10.0, value=float(data.get("bags_eur",0.0)))
    total = float(data["coats_eur"])+float(data["bags_eur"])
    st.metric("Umsatz gesamt", f"{total:,.2f} €")
    return data, total

def _get_unit(unit_id: int):
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT id, unit_type, unit_index, name FROM units WHERE id=?", (unit_id,)).fetchone()
        return dict(zip(["id","unit_type","unit_index","name"], row)) if row else None

def _user_may_edit(unit: dict) -> bool:
    u = st.session_state.get("username","")
    # Betriebsleiter darf alles
    if user_has_function(u, "Betriebsleiter"):
        return True
    # Leiter muss genau dieser Unit zugeordnet sein
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT 1 FROM user_units WHERE user_name=? AND unit_id=?", (u, unit["id"])).fetchone()
        return bool(r)

def render_cashflow_wizard():
    ev = get_current_event()
    if not ev:
        st.info("Kein Event angelegt. Bitte Betriebsleiter startet den Tag.")
        return
    if ev["status"] not in ("IN_PROGRESS","OPEN","DRAFT"):
        st.info(f"Event-Status: {ev['status']} – Änderungen nicht möglich.")
        return

    unit_id = st.session_state.get("cashflow_unit_id")
    if not unit_id:
        st.info("Bitte Einheit in der Übersicht auswählen.")
        return

    unit = _get_unit(unit_id)
    if not unit:
        st.error("Unbekannte Einheit.")
        return

    st.subheader(f"🧭 Wizard – {unit['name']} ({unit['unit_type']})")
    may = _user_may_edit(unit)
    if not may:
        st.error("Keine Berechtigung für diese Einheit.")
        return

    entry = get_entry(ev["id"], unit_id) or {"data":{}, "total":0.0}
    data = dict(entry["data"])

    if unit["unit_type"] == "bar":
        data, total = _bar_form(data)
    elif unit["unit_type"] == "kassa":
        data, total = _kassa_form(data)
    else:
        data, total = _cloak_form(data)

    c1, c2 = st.columns([1,3])
    if c1.button("💾 Speichern", use_container_width=True):
        save_entry(ev["id"], unit_id, st.session_state.get("username",""), data, total, st.session_state.get("username",""))
        st.success("Gespeichert.")
    if c2.button("✅ Abgabe (heute)", use_container_width=True):
        # identisch zu Speichern – kannst du mit Flag ergänzen, wenn du „abgegeben“ markieren willst
        save_entry(ev["id"], unit_id, st.session_state.get("username",""), data, total, st.session_state.get("username",""))
        st.success("Abgegeben.")
