import streamlit as st
import pandas as pd
import datetime
import re
from core.db import conn

# ---------------------------------------------
# Parser für „Coca Cola 0,2l“ → (Name, 0.2, 'l')
# ---------------------------------------------
_UNIT_RE = re.compile(r"\s*(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\s*$", re.IGNORECASE)

def _parse_article_name(raw: str):
    if not raw:
        return ("", None, None)
    s = str(raw).strip()
    m = _UNIT_RE.search(s)
    if not m:
        return (s, None, None)
    amount_str = m.group(1).replace(",", ".")
    unit = m.group(2).lower()
    try:
        amount = float(amount_str)
    except Exception:
        amount = None
    name = _UNIT_RE.sub("", s).strip()
    return (name, amount, unit)

def _to_float(x):
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

# ---------------------------------------------
# Hauptfunktion – Artikelimport
# ---------------------------------------------
def render_import_items():
    st.title("📦 Artikelimport (Excel/CSV)")

    st.markdown("""
    **Erwartetes Format:**
    - **Spalte A:** Artikelname (z. B. „Coca Cola 0,2 l“, „Vodka 2 cl“)
    - **Spalte B:** Bestand (Menge)
    - **Spalte C:** Netto-Einkaufspreis
    - **Spalte D:** (optional – Summe, wird ignoriert)
    """)

    file = st.file_uploader("Datei auswählen", type=["xlsx", "xls", "csv"])
    if not file:
        return

    try:
        if file.name.lower().endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
    except Exception as e:
        st.error(f"Datei konnte nicht gelesen werden: {e}")
        return

    if df.shape[1] < 3:
        st.error("Mindestens 3 Spalten erforderlich (A–C).")
        return

    col_name, col_qty, col_price = df.columns[:3]

    rows = []
    for _, row in df.iterrows():
        raw_name = str(row.get(col_name, "")).strip()
        if not raw_name:
            continue
        name, unit_amount, unit = _parse_article_name(raw_name)
        qty = _to_float(row.get(col_qty))
        price = _to_float(row.get(col_price))
        rows.append({
            "name": name,
            "unit_amount": unit_amount,
            "unit": unit,
            "stock_qty": qty,
            "purchase_price": price,
            "inventur_summe": round(qty * price, 2),
        })

    if not rows:
        st.warning("Keine gültigen Datensätze gefunden.")
        return

    st.subheader("Vorschau")
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    if st.button("✅ Import starten (Upsert)"):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        inserted, updated = 0, 0

        with conn() as cn:
            c = cn.cursor()
            # sicherstellen, dass Tabelle existiert
            c.execute("""
                CREATE TABLE IF NOT EXISTS inventur_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    unit_amount REAL,
                    unit TEXT,
                    stock_qty REAL,
                    purchase_price REAL,
                    last_updated TEXT
                )
            """)

            for r in rows:
                # prüfen, ob Eintrag existiert
                existing = c.execute("""
                    SELECT id FROM inventur_items
                     WHERE name=? AND (unit_amount IS ? OR unit_amount=?)
                       AND (unit IS ? OR unit=?)
                """, (r["name"], r["unit_amount"], r["unit_amount"], r["unit"], r["unit"])).fetchone()

                if existing:
                    c.execute("""
                        UPDATE inventur_items
                           SET stock_qty=?, purchase_price=?, last_updated=?
                         WHERE id=?
                    """, (r["stock_qty"], r["purchase_price"], now, existing[0]))
                    updated += 1
                else:
                    c.execute("""
                        INSERT INTO inventur_items
                            (name, unit_amount, unit, stock_qty, purchase_price, last_updated)
                        VALUES (?,?,?,?,?,?)
                    """, (r["name"], r["unit_amount"], r["unit"], r["stock_qty"], r["purchase_price"], now))
                    inserted += 1
            cn.commit()

        st.success(f"Import abgeschlossen: {inserted} neu · {updated} aktualisiert.")
