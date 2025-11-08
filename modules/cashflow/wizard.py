# modules/cashflow/wizard.py
import streamlit as st

from .models import (
    get_event,
    load_unit_values,
    save_unit_values,
    coat_bag_prices,       # returns (coat_price, bag_price)
)

def render_cashflow_wizard():
    st.subheader("🧭 Erfassung")

    eid = st.session_state.get("cf_event_id")
    sel = st.session_state.get("cf_unit")   # expected: (unit_type, unit_no)

    if not eid:
        st.info("Kein Event ausgewählt.")
        return

    ev = get_event(eid)
    if not ev:
        st.warning("Event nicht gefunden – bitte in der Übersicht erneut wählen.")
        st.session_state.pop("cf_event_id", None)
        return

    if not sel:
        st.info("Bitte in der Übersicht eine Einheit auswählen (Bar/Kassa/Garderobe).")
        return

    utype, uno = sel
    _, ev_day, ev_name, ev_status, *_ = ev
    locked = (ev_status == "approved") and (st.session_state.get("role","").lower() != "admin")

    # Header mit Back
    c1, c2 = st.columns([1,3])
    with c1:
        if st.button("⬅️ Zur Übersicht", use_container_width=True, key=f"cf_wiz_back_{eid}_{utype}_{uno}"):
            st.session_state.pop("cf_unit", None)
            st.experimental_rerun()  # Streamlit v1.40+: st.rerun() wäre auch ok
    with c2:
        st.markdown(f"**Event:** {ev_name} – {ev_day}  |  **Einheit:** {utype.upper()} #{uno}")

    # Bestehende Werte laden
    vals = load_unit_values(eid, utype, uno)

    # Editor je Typ
    if utype == "bar":
        c1, c2, c3, c4 = st.columns(4)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0,
                               value=float(vals.get("cash", 0.0)),
                               disabled=locked, key=f"v_cash_bar_{eid}_{uno}")
        pos1 = c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0,
                               value=float(vals.get("pos1", 0.0)),
                               disabled=locked, key=f"v_pos1_bar_{eid}_{uno}")
        pos2 = c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0,
                               value=float(vals.get("pos2", 0.0)),
                               disabled=locked, key=f"v_pos2_bar_{eid}_{uno}")
        pos3 = c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0,
                               value=float(vals.get("pos3", 0.0)),
                               disabled=locked, key=f"v_pos3_bar_{eid}_{uno}")

        v1, v2 = st.columns([2,1])
        voucher = v1.number_input("Voucher (€)", min_value=0.0, step=10.0,
                                  value=float(vals.get("voucher", 0.0)),
                                  disabled=locked, key=f"v_voucher_bar_{eid}_{uno}")
        tables  = v2.number_input("Tische (Stk)", min_value=0, step=1,
                                  value=int(vals.get("tables", 0) or 0),
                                  disabled=locked, key=f"v_tables_bar_{eid}_{uno}")

        total = float(cash) + float(pos1) + float(pos2) + float(pos3) + float(voucher)
        st.info(f"Umsatz gesamt: **{total:,.2f} €**")

        payload = {
            "cash": cash, "pos1": pos1, "pos2": pos2, "pos3": pos3,
            "voucher": voucher, "tables": tables
        }

    elif utype == "cash":
        c1, c2 = st.columns(2)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0,
                               value=float(vals.get("cash", 0.0)),
                               disabled=locked, key=f"v_cash_cash_{eid}_{uno}")
        card = c2.number_input("Unbar / Karte (€)", min_value=0.0, step=50.0,
                               value=float(vals.get("card", 0.0)),
                               disabled=locked, key=f"v_card_cash_{eid}_{uno}")
        st.info(f"Kassa gesamt: **{(cash+card):,.2f} €**")

        payload = {"cash": cash, "card": card}

    else:  # cloak
        coat_p, bag_p = coat_bag_prices()
        c1, c2 = st.columns(2)
        coats_eur = c1.number_input(f"Jacken/Kleidung (€) – Stückpreis {coat_p:.2f} €",
                                    min_value=0.0, step=10.0,
                                    value=float(vals.get("coats_eur", 0.0)),
                                    disabled=locked, key=f"v_coats_cloak_{eid}_{uno}")
        bags_eur  = c2.number_input(f"Taschen/Rucksäcke (€) – Stückpreis {bag_p:.2f} €",
                                    min_value=0.0, step=10.0,
                                    value=float(vals.get("bags_eur", 0.0)),
                                    disabled=locked, key=f"v_bags_cloak_{eid}_{uno}")
        total = coats_eur + bags_eur
        try:
            coats_qty = int(coats_eur // coat_p) if coat_p > 0 else 0
            bags_qty  = int(bags_eur  // bag_p) if bag_p  > 0 else 0
        except Exception:
            coats_qty = bags_qty = 0
        st.info(f"Garderobe gesamt: **{total:,.2f} €** (≈ Jacken {coats_qty} | Taschen {bags_qty})")

        payload = {"coats_eur": coats_eur, "bags_eur": bags_eur}

    # Actions
    a, b = st.columns([1,1])
    if a.button("💾 Speichern", type="primary", use_container_width=True,
                key=f"cf_save_{eid}_{utype}_{uno}", disabled=locked):
        save_unit_values(eid, utype, uno, payload, st.session_state.get("username") or "unknown")
        st.success("Gespeichert.")

    if b.button("⬅️ Zurück zur Übersicht", use_container_width=True, key=f"cf_back2_{eid}_{utype}_{uno}"):
        st.session_state.pop("cf_unit", None)
        st.experimental_rerun()
