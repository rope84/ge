# modules/cashflow/wizard.py
import streamlit as st
import datetime
from typing import Dict, Tuple
from core.db import conn

BAR_FIELDS  = ["cash", "pos1", "pos2", "pos3", "voucher", "tables"]
CASH_FIELDS = ["cash", "card"]
CLOAK_FIELDS = ["coats_eur", "bags_eur"]

def _prices() -> Tuple[float, float]:
    def _get(key: str, dflt: float) -> float:
        with conn() as cn:
            c = cn.cursor()
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        try:
            return float((r[0] if r else dflt))
        except Exception:
            return dflt
    return _get("conf_coat_price", 2.0), _get("conf_bag_price", 3.0)

def _load(event_id: int, utype: str, uno: int) -> Dict[str, float]:
    fields = BAR_FIELDS if utype=="bar" else CASH_FIELDS if utype=="cash" else CLOAK_FIELDS
    out = {f: 0.0 for f in fields}
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT field, value FROM cashflow_item
            WHERE event_id=? AND unit_type=? AND unit_no=?
        """, (event_id, utype, uno)).fetchall()
    for f, v in rows:
        try:
            out[f] = float(v)
        except Exception:
            pass
    return out

def _save(event_id: int, utype: str, uno: int, data: Dict[str, float], user: str):
    with conn() as cn:
        c = cn.cursor()
        for k, v in data.items():
            c.execute("""
                INSERT INTO cashflow_item(event_id, unit_type, unit_no, field, value, updated_by, updated_at)
                VALUES(?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(event_id, unit_type, unit_no, field)
                DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at
            """, (event_id, utype, uno, k, float(v or 0.0), user))
        cn.commit()

def render_cashflow_wizard(is_mgr: bool = False):
    st.header("🧭 Wizard – Abrechnung erfassen")

    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event angelegt. Bitte im Tab **Übersicht** den Tag starten.")
        return

    with conn() as cn:
        c = cn.cursor()
        evt = c.execute("SELECT id, event_date, name, status FROM events WHERE id=?", (ev_id,)).fetchone()

    if not evt:
        st.warning("Event nicht gefunden – bitte im Tab Übersicht neu öffnen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    unit_sel = st.session_state.get("cf_unit")
    if not unit_sel:
        st.info("Bitte wähle zuerst deine Einheit im Tab **Übersicht**.")
        return

    utype, uno = unit_sel
    locked = (ev_status == "approved") and (not is_mgr)
    user = st.session_state.get("username") or "unknown"
    vals = _load(ev_id, utype, uno)

    st.markdown(f"#### {utype.upper()} #{uno}")

    if utype == "bar":
        c1,c2,c3,c4 = st.columns(4)
        v_cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), disabled=locked, key=f"bar_cash_{ev_id}_{uno}")
        v_pos1 = c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0, value=float(vals["pos1"]), disabled=locked, key=f"bar_pos1_{ev_id}_{uno}")
        v_pos2 = c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0, value=float(vals["pos2"]), disabled=locked, key=f"bar_pos2_{ev_id}_{uno}")
        v_pos3 = c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0, value=float(vals["pos3"]), disabled=locked, key=f"bar_pos3_{ev_id}_{uno}")
        r1, r2 = st.columns([2,1])
        v_voucher = r1.number_input("Voucher (€)", min_value=0.0, step=10.0, value=float(vals["voucher"]), disabled=locked, key=f"bar_voucher_{ev_id}_{uno}")
        v_tables = r2.number_input("Tische (Stk)", min_value=0, step=1, value=int(vals["tables"]), disabled=locked, key=f"bar_tables_{ev_id}_{uno}")
        total = v_cash + v_pos1 + v_pos2 + v_pos3 + v_voucher
        st.info(f"Umsatz gesamt: **{total:,.2f} €**", icon="💶")
        payload = {"cash": v_cash, "pos1": v_pos1, "pos2": v_pos2, "pos3": v_pos3, "voucher": v_voucher, "tables": v_tables}

    elif utype == "cash":
        c1,c2 = st.columns(2)
        v_cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), disabled=locked, key=f"cash_cash_{ev_id}_{uno}")
        v_card = c2.number_input("Unbar / Karte (€)", min_value=0.0, step=50.0, value=float(vals["card"]), disabled=locked, key=f"cash_card_{ev_id}_{uno}")
        st.info(f"Kassa gesamt: **{(v_cash+v_card):,.2f} €**", icon="🧾")
        payload = {"cash": v_cash, "card": v_card}

    else:
        coat_p, bag_p = _prices()
        c1,c2 = st.columns(2)
        v_coats = c1.number_input(f"Jacken/Kleidung (€) – Stückpreis {coat_p:.2f} €", min_value=0.0, step=10.0, value=float(vals["coats_eur"]), disabled=locked, key=f"cloak_coats_{ev_id}_{uno}")
        v_bags  = c2.number_input(f"Taschen/Rucksäcke (€) – Stückpreis {bag_p:.2f} €", min_value=0.0, step=10.0, value=float(vals["bags_eur"]),  disabled=locked, key=f"cloak_bags_{ev_id}_{uno}")
        total = v_coats + v_bags
        # Überschlagsmenge
        qty_coats = int(v_coats // coat_p) if coat_p > 0 else 0
        qty_bags  = int(v_bags  // bag_p)  if bag_p  > 0 else 0
        st.info(f"Garderobe gesamt: **{total:,.2f} €** (≈ Jacken {qty_coats} | Taschen {qty_bags})", icon="🧥")
        payload = {"coats_eur": v_coats, "bags_eur": v_bags}

    colA, colB = st.columns([1,1])
    if colA.button("⬅️ Zur Übersicht", use_container_width=True):
        st.session_state.pop("cf_unit", None)
        st.session_state["cf_active_tab"] = "home"
        st.rerun()

    if not locked and colB.button("💾 Speichern", type="primary", use_container_width=True):
        _save(ev_id, utype, uno, payload, user)
        st.success("Gespeichert.")
