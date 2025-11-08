import streamlit as st
from typing import Dict
from .utils import (
    counts_from_meta,
    wardrobe_prices,
    get_event,
)
from core.db import conn
import datetime

BAR_FIELDS  = ["cash", "pos1", "pos2", "pos3", "voucher", "tables"]
CASH_FIELDS = ["cash", "card"]
CLOAK_FIELDS = ["coats_eur", "bags_eur"]

def _load_unit_values(event_id: int, unit_type: str, unit_no: int) -> Dict[str, float]:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT field, value FROM cashflow_item
            WHERE event_id=? AND unit_type=? AND unit_no=?
        """, (event_id, unit_type, unit_no)).fetchall()
    out = {f: 0.0 for f in (BAR_FIELDS if unit_type=="bar" else CASH_FIELDS if unit_type=="cash" else CLOAK_FIELDS)}
    for f, v in rows:
        try:
            out[f] = float(v)
        except Exception:
            pass
    return out

def _save_unit_values(event_id: int, unit_type: str, unit_no: int, data: Dict[str, float], username: str):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        for k, v in data.items():
            c.execute("""
                INSERT INTO cashflow_item(event_id, unit_type, unit_no, field, value, updated_by, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(event_id, unit_type, unit_no, field)
                DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at
            """, (event_id, unit_type, unit_no, k, float(v or 0.0), username, now))
        cn.commit()

def render_cashflow_wizard(is_mgr: bool, is_bar: bool, is_kas: bool, is_clo: bool):
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event angelegt. Bitte Betriebsleiter startet den Tag.")
        return

    evt = get_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut wählen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status, *_ = evt
    locked = (ev_status == "approved") and (not is_mgr)

    st.markdown(f"**Event:** {ev_name} – {ev_day}  "
                f"{'(gesperrt – freigegeben)' if locked else ''}")

    sel = st.session_state.get("cf_unit")  # ("bar"| "cash"|"cloak", no)
    if not sel:
        st.info("Wähle in der Übersicht eine Einheit aus (Kachel „Bearbeiten“).")
        return

    unit_type, unit_no = sel
    # Einheiten-Limit (nicht mehr als in Meta definiert)
    cnt = counts_from_meta()
    max_allowed = {"bar": cnt["bars"], "cash": cnt["registers"], "cloak": cnt["cloakrooms"]}
    if unit_no < 1 or unit_no > max_allowed.get(unit_type, 0):
        st.error("Diese Einheit ist für das Event nicht zulässig.")
        return

    st.markdown(f"#### {unit_type.upper()} #{unit_no}")
    vals = _load_unit_values(ev_id, unit_type, unit_no)

    if unit_type == "bar":
        c1,c2,c3,c4 = st.columns(4)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), disabled=locked)
        pos1 = c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0, value=float(vals["pos1"]), disabled=locked)
        pos2 = c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0, value=float(vals["pos2"]), disabled=locked)
        pos3 = c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0, value=float(vals["pos3"]), disabled=locked)
        v1, v2 = st.columns([2,1])
        voucher = v1.number_input("Voucher (€)", min_value=0.0, step=10.0, value=float(vals["voucher"]), disabled=locked)
        tables = v2.number_input("Tische (Stk)", min_value=0, step=1, value=int(vals["tables"]), disabled=locked)
        total = cash + pos1 + pos2 + pos3 + voucher
        st.info(f"Umsatz gesamt: **{total:,.2f} €**", icon="💶")
        payload = {"cash": cash, "pos1": pos1, "pos2": pos2, "pos3": pos3, "voucher": voucher, "tables": tables}

    elif unit_type == "cash":
        c1,c2 = st.columns(2)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), disabled=locked)
        card = c2.number_input("Unbar / Karte (€)", min_value=0.0, step=50.0, value=float(vals["card"]), disabled=locked)
        st.info(f"Kassa gesamt: **{(cash+card):,.2f} €**", icon="🧾")
        payload = {"cash": cash, "card": card}

    else:
        coat_p, bag_p = wardrobe_prices()
        c1,c2 = st.columns(2)
        coats_eur = c1.number_input(f"Jacken/Kleidung (€) – Stückpreis {coat_p:.2f} €",
                                    min_value=0.0, step=10.0, value=float(vals["coats_eur"]), disabled=locked)
        bags_eur  = c2.number_input(f"Taschen/Rucksäcke (€) – Stückpreis {bag_p:.2f} €",
                                    min_value=0.0, step=10.0, value=float(vals["bags_eur"]), disabled=locked)
        total = coats_eur + bags_eur
        coats_qty = int(coats_eur // coat_p) if coat_p > 0 else 0
        bags_qty  = int(bags_eur  // bag_p)  if bag_p  > 0 else 0
        st.info(f"Garderobe gesamt: **{total:,.2f} €** (≈ Jacken {coats_qty} | Taschen {bags_qty})", icon="🧥")
        payload = {"coats_eur": coats_eur, "bags_eur": bags_eur}

    cA, cB = st.columns([1,1])
    if cA.button("⬅️ Zur Übersicht", use_container_width=True):
        st.session_state.pop("cf_unit", None)
        st.session_state["cf_active_tab"] = "home"
        st.rerun()

    if not locked and cB.button("💾 Speichern", type="primary", use_container_width=True):
        _save_unit_values(ev_id, unit_type, unit_no, payload, st.session_state.get("username") or "unknown")
        st.success("Gespeichert.")
