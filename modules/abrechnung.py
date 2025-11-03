# abrechnung.py
import streamlit as st
from datetime import date
from core.ui_theme import page_header, section_title, metric_card


# -----------------------------------------------
# Hilfsfunktionen für Settings (Preise aus Admin)
# -----------------------------------------------
def _coat_price():
    return float(st.session_state.get("conf_coat_price", 2.0))

def _bag_price():
    return float(st.session_state.get("conf_bag_price", 3.0))


# -----------------------------------------------
# Initialisierung der Session-State-Struktur
# -----------------------------------------------
def _init_day_state():
    ss = st.session_state
    if "abr" not in ss:
        ss.abr = {}
    d = ss.abr

    # Kopf
    d.setdefault("date", date.today())
    d.setdefault("event", "")
    d.setdefault("note", "")

    # Bars 1..7
    for i in range(1, 8):
        b = d.setdefault(f"bar{i}", {})
        b.setdefault("cash", 0.0)
        b.setdefault("pos1", 0.0)
        b.setdefault("pos2", 0.0)
        b.setdefault("pos3", 0.0)
        b.setdefault("voucher", 0.0)
        b.setdefault("tables", 0)

    # Eingang (Kassen)
    ent = d.setdefault("entrance", {})
    for k in (1, 2, 3):
        e = ent.setdefault(f"kassa{k}", {})
        e.setdefault("cash", 0.0)
        e.setdefault("card", 0.0)

    # Garderobe
    gar = d.setdefault("cloak", {})
    gar.setdefault("coats_eur", 0.0)
    gar.setdefault("bags_eur", 0.0)

    # Ausgaben
    d.setdefault("expenses", [])

    ss.abr = d


# -----------------------------------------------
# Berechnung pro Bar
# -----------------------------------------------
def _bar_total(bar: dict) -> float:
    return float(bar["cash"]) + float(bar["pos1"]) + float(bar["pos2"]) + float(bar["pos3"]) + float(bar["voucher"])


# -----------------------------------------------
# Haupt-Renderfunktion
# -----------------------------------------------
def render_abrechnung(role: str, scope: str):
    # Einheitlicher Seitenkopf mit Icon
    page_header("💰 Abrechnung", "Bars, Eingang & Garderobe erfassen")

    # Session-State initialisieren
    _init_day_state()
    d = st.session_state.abr

    # Kopfzeile (Datum / Event / Notiz)
    section_title("Tagesdaten")
    kc1, kc2, kc3 = st.columns([1, 1.2, 1.2])
    d["date"] = kc1.date_input("Datum", value=d.get("date", date.today()), key="abr_date")
    d["event"] = kc2.text_input("Öffnungstag / Event", value=d.get("event", ""), key="abr_event", placeholder="z.B. OZ / Halloween")
    d["note"] = kc3.text_input("Notiz", value=d.get("note", ""), key="abr_note", placeholder="Optionaler Kommentar")

    st.divider()

    # Tabs: Bars 1..7 + Eingang + Garderobe + Abzüge
    tab_labels = [f"Bar {i}" for i in range(1, 8)] + ["Eingang", "Garderobe", "Abzüge"]
    tabs = st.tabs(tab_labels)

    # -----------------------------
    # BAR-TABS (1..7)
    # -----------------------------
    for idx, i in enumerate(range(1, 8)):
        with tabs[idx]:
            bar = d[f"bar{i}"]
            st.caption(f"Bar {i} (Barleiter: –)")

            # Eingaben für Umsätze
            r1c1, r1c2, r1c3, r1c4 = st.columns(4)
            bar["cash"] = r1c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(bar["cash"]), key=f"bar{i}_cash")
            bar["pos1"] = r1c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0, value=float(bar["pos1"]), key=f"bar{i}_pos1")
            bar["pos2"] = r1c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0, value=float(bar["pos2"]), key=f"bar{i}_pos2")
            bar["pos3"] = r1c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0, value=float(bar["pos3"]), key=f"bar{i}_pos3")

            # Eingaben für Voucher + Tische
            r2c1, r2c2 = st.columns([2, 1])
            bar["voucher"] = r2c1.number_input("Voucher (€)", min_value=0.0, step=10.0, value=float(bar["voucher"]), key=f"bar{i}_voucher")
            bar["tables"] = int(r2c2.number_input("Tische (Stk)", min_value=0, step=1, value=int(bar["tables"]), key=f"bar{i}_tables"))

            # Kompakte Kennzahl-Karte pro Bar
            total_i = _bar_total(bar)
            metric_card(f"Bar {i} – Umsatz gesamt", f"{total_i:,.2f} €", "inkl. Voucher")

    # -----------------------------
    # EINGANG (Kassen)
    # -----------------------------
    with tabs[7]:
        section_title("Eingang (Kassen)")
        ent = d["entrance"]

        for k in (1, 2, 3):
            st.subheader(f"Kassa {k}")
            ec1, ec2 = st.columns(2)
            ent[f"kassa{k}"]["cash"] = ec1.number_input(f"Barumsatz (€)", min_value=0.0, step=50.0,
                                                        value=float(ent[f'kassa{k}']["cash"]), key=f"kassa{k}_cash")
            ent[f"kassa{k}"]["card"] = ec2.number_input(f"Unbar / Bankomat (€)", min_value=0.0, step=50.0,
                                                        value=float(ent[f'kassa{k}']["card"]), key=f"kassa{k}_card")
            st.markdown("---")

        ksum = sum(float(ent[f"kassa{k}"]["cash"]) + float(ent[f"kassa{k}"]["card"]) for k in (1, 2, 3))
        metric_card("Eingang – Umsatz gesamt", f"{ksum:,.2f} €", "Kassa 1–3 (Bar + Unbar)")

    # -----------------------------
    # GARDEROBE
    # -----------------------------
    with tabs[8]:
        section_title("Garderobe")
        coat_p, bag_p = _coat_price(), _bag_price()

        gc1, gc2 = st.columns(2)
        d["cloak"]["coats_eur"] = gc1.number_input(f"Jacken/Kleidung (€) – Stückpreis {coat_p:.2f} €",
                                                   min_value=0.0, step=10.0, value=float(d['cloak']["coats_eur"]), key="cloak_coats_eur")
        d["cloak"]["bags_eur"] = gc2.number_input(f"Taschen/Rucksäcke (€) – Stückpreis {bag_p:.2f} €",
                                                  min_value=0.0, step=10.0, value=float(d['cloak']["bags_eur"]), key="cloak_bags_eur")

        coats_qty = int(d["cloak"]["coats_eur"] // coat_p) if coat_p > 0 else 0
        bags_qty = int(d["cloak"]["bags_eur"] // bag_p) if bag_p > 0 else 0
        gsum = float(d["cloak"]["coats_eur"]) + float(d["cloak"]["bags_eur"])

        metric_card("Garderobe – Umsatz gesamt", f"{gsum:,.2f} €", f"≈ Jacken: {coats_qty} | Taschen: {bags_qty}")

    # -----------------------------
    # ABZÜGE / AUSGABEN
    # -----------------------------
    with tabs[9]:
        section_title("Ausgaben / Abzüge")
        exps = d["expenses"]

        cadd, crem = st.columns([1, 1])
        if cadd.button("➕ Position hinzufügen", key="exp_add"):
            exps.append({"name": "", "amount": 0.0})
        if crem.button("➖ letzte Position entfernen", key="exp_remove") and exps:
            exps.pop()

        for idx, item in enumerate(exps):
            e1, e2 = st.columns([3, 1])
            item["name"] = e1.text_input("Bezeichnung", value=item.get("name", ""), key=f"exp_name_{idx}", placeholder="z.B. DJ-Gage, Security …")
            item["amount"] = e2.number_input("Betrag (€)", min_value=0.0, step=10.0,
                                             value=float(item.get("amount", 0.0)), key=f"exp_amt_{idx}")
            st.markdown("---")

        total_exp = sum(float(x.get("amount", 0.0)) for x in exps)
        metric_card("Summe Abzüge", f"{total_exp:,.2f} €", "Gesamt aller Ausgaben")

    # -----------------------------
    # Aktionen (Speichern / Abschließen)
    # -----------------------------
    st.divider()
    b1, b2 = st.columns([1, 3])
    if b1.button("💾 Zwischenspeichern", use_container_width=True):
        st.success("Lokale Eingaben aktualisiert. (DB-Speicherlogik kann hier ergänzt werden)")
    if b2.button("✅ Tag abschließen", use_container_width=True):
        st.success("Tag abgeschlossen. (Finale DB-Speicherung/Export hier einbauen)")
