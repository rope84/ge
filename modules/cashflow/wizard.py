# modules/cashflow/wizard.py
import streamlit as st
import datetime
from core.db import conn

# ---------- lokale DB-Helfer (unabhängig von models.py) ----------
BAR_FIELDS   = ["cash", "pos1", "pos2", "pos3", "voucher", "tables"]
CASH_FIELDS  = ["cash", "card"]
CLOAK_FIELDS = ["coats_eur", "bags_eur"]

def _get_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, event_date, name, status, created_by, created_at, approved_by, approved_at "
            "FROM events WHERE id=?",
            (event_id,),
        ).fetchone()

def _get_prices() -> tuple[float, float]:
    def _meta(key: str):
        with conn() as cn:
            c = cn.cursor()
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return r[0] if r else None
    def _f(key: str, dflt: float) -> float:
        v = _meta(key)
        try:
            return float(str(v).replace(",", ".")) if v is not None else dflt
        except Exception:
            return dflt
    return _f("conf_coat_price", 2.0), _f("conf_bag_price", 3.0)

def _load_unit_values(event_id: int, unit_type: str, unit_no: int) -> dict[str, float]:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT field, value FROM cashflow_item
            WHERE event_id=? AND unit_type=? AND unit_no=?
        """, (event_id, unit_type, unit_no)).fetchall()
    base = (
        {f: 0.0 for f in BAR_FIELDS} if unit_type == "bar"
        else {f: 0.0 for f in CASH_FIELDS} if unit_type == "cash"
        else {f: 0.0 for f in CLOAK_FIELDS}
    )
    for f, v in rows:
        try:
            base[f] = float(v)
        except Exception:
            pass
    return base

def _save_unit_values(event_id: int, unit_type: str, unit_no: int, data: dict[str, float], username: str):
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
        # Audit
        c.execute(
            "INSERT INTO audit_log(ts, user, action, details) VALUES(?,?,?,?)",
            (now, username, "unit_save", f"{event_id} {unit_type}#{unit_no} -> {data}")
        )
        cn.commit()

# ---------- UI ----------
def render_cashflow_wizard():
    st.subheader("🧭 Erfassung")

    eid = st.session_state.get("cf_event_id")
    sel = st.session_state.get("cf_unit")        # erwartet: (unit_type, unit_no)

    if not eid:
        st.info("Kein Event ausgewählt.")
        return
    ev = _get_event(eid)
    if not ev:
        st.warning("Event nicht gefunden – bitte in der Übersicht erneut wählen.")
        st.session_state.pop("cf_event_id", None)
        st.rerun()
        return
    if not sel:
        st.info("Bitte in der Übersicht eine Einheit auswählen (Bar/Kassa/Garderobe).")
        return

    utype, uno = sel
    _, ev_day, ev_name, ev_status, *_ = ev
    # Sperre für Nicht-Admins bei freigegebenem Event
    is_admin = (st.session_state.get("role","").lower() == "admin") or \
               ("admin" in (st.session_state.get("functions","") or "").lower())
    locked = (ev_status == "approved") and (not is_admin)

    # Header + Back
    c1, c2 = st.columns([1,3])
    with c1:
        if st.button("⬅️ Zur Übersicht", use_container_width=True,
                     key=f"cf_wiz_back_{eid}_{utype}_{uno}"):
            st.session_state.pop("cf_unit", None)
            st.rerun()
    with c2:
        st.markdown(f"**Event:** {ev_name} – {ev_day}  |  **Einheit:** {utype.upper()} #{uno}")

    # Werte laden
    vals = _load_unit_values(eid, utype, uno)

    # Editor
    if utype == "bar":
        c1, c2, c3, c4 = st.columns(4)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0,
                               value=float(vals["cash"]), disabled=locked,
                               key=f"v_cash_bar_{eid}_{uno}")
        pos1 = c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0,
                               value=float(vals["pos1"]), disabled=locked,
                               key=f"v_pos1_bar_{eid}_{uno}")
        pos2 = c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0,
                               value=float(vals["pos2"]), disabled=locked,
                               key=f"v_pos2_bar_{eid}_{uno}")
        pos3 = c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0,
                               value=float(vals["pos3"]), disabled=locked,
                               key=f"v_pos3_bar_{eid}_{uno}")
        v1, v2 = st.columns([2,1])
        voucher = v1.number_input("Voucher (€)", min_value=0.0, step=10.0,
                                  value=float(vals["voucher"]), disabled=locked,
                                  key=f"v_voucher_bar_{eid}_{uno}")
        tables = v2.number_input("Tische (Stk)", min_value=0, step=1,
                                  value=int(vals["tables"]), disabled=locked,
                                  key=f"v_tables_bar_{eid}_{uno}")
        total = float(cash)+float(pos1)+float(pos2)+float(pos3)+float(voucher)
        st.info(f"Umsatz gesamt: **{total:,.2f} €**")
        payload = {"cash": cash, "pos1": pos1, "pos2": pos2, "pos3": pos3,
                   "voucher": voucher, "tables": tables}

    elif utype == "cash":
        c1, c2 = st.columns(2)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0,
                               value=float(vals["cash"]), disabled=locked,
                               key=f"v_cash_cash_{eid}_{uno}")
        card = c2.number_input("Unbar / Karte (€)", min_value=0.0, step=50.0,
                               value=float(vals["card"]), disabled=locked,
                               key=f"v_card_cash_{eid}_{uno}")
        st.info(f"Kassa gesamt: **{(cash+card):,.2f} €**")
        payload = {"cash": cash, "card": card}

    else:  # cloak
        coat_p, bag_p = _get_prices()
        c1, c2 = st.columns(2)
        coats_eur = c1.number_input(
            f"Jacken/Kleidung (€) – Stückpreis {coat_p:.2f} €",
            min_value=0.0, step=10.0, value=float(vals["coats_eur"]),
            disabled=locked, key=f"v_coats_cloak_{eid}_{uno}"
        )
        bags_eur = c2.number_input(
            f"Taschen/Rucksäcke (€) – Stückpreis {bag_p:.2f} €",
            min_value=0.0, step=10.0, value=float(vals["bags_eur"]),
            disabled=locked, key=f"v_bags_cloak_{eid}_{uno}"
        )
        total = coats_eur + bags_eur
        try:
            coats_qty = int(coats_eur // coat_p) if coat_p > 0 else 0
            bags_qty  = int(bags_eur // bag_p)  if bag_p  > 0 else 0
        except Exception:
            coats_qty = bags_qty = 0
        st.info(f"Garderobe gesamt: **{total:,.2f} €** (≈ Jacken {coats_qty} | Taschen {bags_qty})")
        payload = {"coats_eur": coats_eur, "bags_eur": bags_eur}

    # Actions
    a, b = st.columns([1,1])
    if a.button("💾 Speichern", type="primary", use_container_width=True,
                key=f"cf_save_{eid}_{utype}_{uno}", disabled=locked):
        _save_unit_values(eid, utype, uno, payload, st.session_state.get("username") or "unknown")
        st.success("Gespeichert.")

    if b.button("⬅️ Zur Übersicht", use_container_width=True,
                key=f"cf_back2_{eid}_{utype}_{uno}"):
        st.session_state.pop("cf_unit", None)
        st.rerun()
