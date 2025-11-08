# modules/cashflow/wizard.py
import streamlit as st
import datetime
from typing import Dict
from core.db import conn

BAR_FIELDS  = ["cash", "pos1", "pos2", "pos3", "voucher", "tables"]
CASH_FIELDS = ["cash", "card"]
CLOAK_FIELDS= ["coats_eur", "bags_eur"]

def _ensure_schema():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id  INTEGER NOT NULL,
                unit_type TEXT NOT NULL,   -- bar|cash|cloak
                unit_no   INTEGER NOT NULL,
                field     TEXT NOT NULL,
                value     REAL  NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TEXT,
                UNIQUE(event_id, unit_type, unit_no, field)
            )
        """)
        cn.commit()

def _get_prices() -> tuple[float, float]:
    with conn() as cn:
        c = cn.cursor()
        coat = c.execute("SELECT value FROM meta WHERE key='conf_coat_price'").fetchone()
        bag  = c.execute("SELECT value FROM meta WHERE key='conf_bag_price'").fetchone()
    def _f(x, dflt):
        try:
            return float(str(x[0]).replace(",", ".")) if x and x[0] is not None else dflt
        except Exception:
            return dflt
    return _f(coat, 2.0), _f(bag, 3.0)

def _load(event_id: int, unit_type: str, unit_no: int) -> Dict[str, float]:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            "SELECT field, value FROM cashflow_item WHERE event_id=? AND unit_type=? AND unit_no=?",
            (event_id, unit_type, unit_no)
        ).fetchall()
    fields = BAR_FIELDS if unit_type == "bar" else CASH_FIELDS if unit_type == "cash" else CLOAK_FIELDS
    out = {f: 0.0 for f in fields}
    for f, v in rows:
        try:
            out[f] = float(v)
        except Exception:
            pass
    return out

def _save(event_id: int, unit_type: str, unit_no: int, data: Dict[str, float], username: str):
    with conn() as cn:
        c = cn.cursor()
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for k, v in data.items():
            c.execute("""
                INSERT INTO cashflow_item(event_id, unit_type, unit_no, field, value, updated_by, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(event_id, unit_type, unit_no, field)
                DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at
            """, (event_id, unit_type, unit_no, k, float(v or 0.0), username, now))
        cn.commit()

def render_cashflow_wizard() -> bool:
    """Gibt True zurück, wenn 'Zur Übersicht' gedrückt wurde (damit der Aufrufer die View umschaltet)."""
    _ensure_schema()

    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event angelegt. (Betriebsleiter: bitte unter 'Event' starten.)")
        return False

    sel = st.session_state.get("cf_unit")
    if not sel:
        st.caption("Wähle unter 'Einheiten & Kacheln' eine Einheit aus.")
        return False

    unit_type, unit_no = sel
    username = st.session_state.get("username") or "unknown"

    st.markdown(f"#### {unit_type.upper()} #{unit_no}")

    vals = _load(ev_id, unit_type, unit_no)

    if unit_type == "bar":
        c1,c2,c3,c4 = st.columns(4)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), key=f"bar_cash_{ev_id}_{unit_no}")
        pos1 = c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0, value=float(vals["pos1"]), key=f"bar_pos1_{ev_id}_{unit_no}")
        pos2 = c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0, value=float(vals["pos2"]), key=f"bar_pos2_{ev_id}_{unit_no}")
        pos3 = c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0, value=float(vals["pos3"]), key=f"bar_pos3_{ev_id}_{unit_no}")
        v1, v2 = st.columns([2,1])
        voucher = v1.number_input("Voucher (€)", min_value=0.0, step=10.0, value=float(vals["voucher"]), key=f"bar_voucher_{ev_id}_{unit_no}")
        tables  = v2.number_input("Tische (Stk)", min_value=0, step=1, value=int(vals["tables"]), key=f"bar_tables_{ev_id}_{unit_no}")
        total = float(cash)+float(pos1)+float(pos2)+float(pos3)+float(voucher)
        st.info(f"Umsatz gesamt: **{total:,.2f} €**", icon="💶")
        payload = {"cash": cash, "pos1": pos1, "pos2": pos2, "pos3": pos3, "voucher": voucher, "tables": tables}

    elif unit_type == "cash":
        c1,c2 = st.columns(2)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), key=f"kas_cash_{ev_id}_{unit_no}")
        card = c2.number_input("Unbar / Karte (€)", min_value=0.0, step=50.0, value=float(vals["card"]), key=f"kas_card_{ev_id}_{unit_no}")
        st.info(f"Kassa gesamt: **{(cash+card):,.2f} €**", icon="🧾")
        payload = {"cash": cash, "card": card}

    else:  # cloak
        coat_p, bag_p = _get_prices()
        c1,c2 = st.columns(2)
        coats_eur = c1.number_input(f"Jacken/Kleidung (€) – Stückpreis {coat_p:.2f} €", min_value=0.0, step=10.0, value=float(vals["coats_eur"]), key=f"cloak_coats_{ev_id}_{unit_no}")
        bags_eur  = c2.number_input(f"Taschen/Rucksäcke (€) – Stückpreis {bag_p:.2f} €", min_value=0.0, step=10.0, value=float(vals["bags_eur"]), key=f"cloak_bags_{ev_id}_{unit_no}")
        total = coats_eur + bags_eur
        try:
            coats_qty = int(coats_eur // coat_p) if coat_p > 0 else 0
            bags_qty  = int(bags_eur  // bag_p)  if bag_p  > 0 else 0
        except Exception:
            coats_qty = bags_qty = 0
        st.info(f"Garderobe gesamt: **{total:,.2f} €** (≈ Jacken {coats_qty} | Taschen {bags_qty})", icon="🧥")
        payload = {"coats_eur": coats_eur, "bags_eur": bags_eur}

    colA, colB = st.columns([1,1])
    back_pressed = colA.button("⬅️ Zur Übersicht", use_container_width=True, key=f"back_{ev_id}_{unit_type}_{unit_no}")
    saved = colB.button("💾 Speichern", type="primary", use_container_width=True, key=f"save_{ev_id}_{unit_type}_{unit_no}")

    if saved:
        _save(ev_id, unit_type, unit_no, payload, username)
        st.success("Gespeichert.")

    return bool(back_pressed)
