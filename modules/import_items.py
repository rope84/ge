# modules/import_items.py
import streamlit as st
import pandas as pd
import datetime
import re
from typing import List, Optional, Tuple
from core.db import conn

# ---------------------------------------------
# Helpers: Tabellen sicherstellen / Spalten nachrüsten
# ---------------------------------------------
def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()
        # Inventur-Artikel
        c.execute("""
            CREATE TABLE IF NOT EXISTS inventur_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                unit_amount REAL,
                unit TEXT,
                stock_qty REAL NOT NULL DEFAULT 0,
                purchase_price REAL NOT NULL DEFAULT 0,
                "group" TEXT,
                last_updated TEXT
            )
        """)
        # Artikelgruppen
        c.execute("""
            CREATE TABLE IF NOT EXISTS item_groups (
                name TEXT PRIMARY KEY
            )
        """)
        # Standard-Gruppen – nur einmalig
        defaults = ["alkoholfrei", "bier", "wein", "schaumwein"]
        for g in defaults:
            try:
                c.execute("INSERT INTO item_groups(name) VALUES (?)", (g,))
            except Exception:
                pass
        cn.commit()

def _get_groups() -> List[str]:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("SELECT name FROM item_groups ORDER BY name").fetchall()
        return [r[0] for r in rows]

def _add_group(name: str) -> bool:
    if not name:
        return False
    with conn() as cn:
        try:
            cn.execute("INSERT INTO item_groups(name) VALUES (?)", (name.strip(),))
            cn.commit()
            return True
        except Exception:
            return False

def _delete_group(name: str) -> bool:
    if not name:
        return False
    with conn() as cn:
        try:
            cn.execute("DELETE FROM item_groups WHERE name=?", (name,))
            cn.commit()
            return True
        except Exception:
            return False

# ---------------------------------------------
# Parser für „Coca Cola 0,2 l“ → (Name, 0.2, 'l')
# ---------------------------------------------
_UNIT_RE = re.compile(r"\s*(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\s*$", re.IGNORECASE)

def _parse_article_name(raw: str) -> Tuple[str, Optional[float], Optional[str]]:
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

def _to_float(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def _guess_group(name: str) -> Optional[str]:
    if not name:
        return None
    n = name.lower()
    if "schaum" in n or "prosecco" in n or "sekt" in n or "champ" in n:
        return "schaumwein"
    if "wein" in n or "merlot" in n or "riesling" in n:
        return "wein"
    if "bier" in n or "radler" in n or "ipa" in n or "stout" in n:
        return "bier"
    if any(k in n for k in ["wasser", "cola", "sprite", "almdudler", "saft", "juice", "ice tea", "eistee", "tonic", "soda"]):
        return "alkoholfrei"
    return None

# ---------------------------------------------
# DB-Zugriffe Inventur-Artikel
# ---------------------------------------------
def _fetch_items_df() -> pd.DataFrame:
    with conn() as cn:
        return pd.read_sql(
            'SELECT id, name, unit_amount, unit, stock_qty, purchase_price, "group", last_updated FROM inventur_items ORDER BY name',
            cn
        )

def _upsert_item(row: dict):
    """Upsert nach (name, unit_amount, unit)."""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        ex = c.execute("""
            SELECT id FROM inventur_items
            WHERE name=? AND (unit_amount IS ? OR unit_amount=?) AND (unit IS ? OR unit=?)
        """, (row["name"], row["unit_amount"], row["unit_amount"], row["unit"], row["unit"])).fetchone()
        if ex:
            c.execute("""
                UPDATE inventur_items
                   SET stock_qty=?, purchase_price=?, "group"=?, last_updated=?
                 WHERE id=?
            """, (row["stock_qty"], row["purchase_price"], row.get("group"), now, ex[0]))
        else:
            c.execute("""
                INSERT INTO inventur_items (name, unit_amount, unit, stock_qty, purchase_price, "group", last_updated)
                VALUES (?,?,?,?,?,?,?)
            """, (row["name"], row["unit_amount"], row["unit"], row["stock_qty"], row["purchase_price"], row.get("group"), now))
        cn.commit()

def _update_item_by_id(itm: dict):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        cn.execute("""
            UPDATE inventur_items
               SET name=?, unit_amount=?, unit=?, stock_qty=?, purchase_price=?, "group"=?, last_updated=?
             WHERE id=?
        """, (itm["name"], itm["unit_amount"], itm["unit"], itm["stock_qty"], itm["purchase_price"], itm.get("group"), now, itm["id"]))
        cn.commit()

def _delete_items_by_ids(ids: List[int]):
    if not ids:
        return
    with conn() as cn:
        q = "DELETE FROM inventur_items WHERE id IN (%s)" % ",".join(["?"]*len(ids))
        cn.execute(q, ids)
        cn.commit()

# ---------------------------------------------
# UI
# ---------------------------------------------
def _divider():
    st.markdown("<hr style='opacity:0.1;'>", unsafe_allow_html=True)

def render_import_items():
    _ensure_tables()

    st.markdown("## 📦 Artikelimport & Verwaltung")
    st.caption("Excel/CSV importieren, Artikel prüfen/ändern, Gruppen verwalten.")

    # --- Layout: Upload links / Gruppen rechts
    left, right = st.columns([2, 1], gap="large")

    with left:
        st.subheader("1) Datei hochladen")
        st.write("**Format:** Spalte **A** Name (z. B. „Coca Cola 0,2 l“), **B** Bestand, **C** Netto-EK, **D** (optional, ignoriert).")
        file = st.file_uploader("Datei auswählen", type=["xlsx", "xls", "csv"])
        zero_all = st.checkbox("Alle Bestände (Stock) beim Import auf **0** setzen", value=False)
        st.caption("Tipp: „Bestand = letzter Inventurstand“. Du kannst ihn hier bewusst auf 0 setzen.")

        parsed_df = None
        groups = _get_groups()

        if file:
            try:
                if file.name.lower().endswith(".csv"):
                    raw_df = pd.read_csv(file)
                else:
                    raw_df = pd.read_excel(file)
            except Exception as e:
                st.error(f"Datei konnte nicht gelesen werden: {e}")
                raw_df = None

            if raw_df is not None:
                if raw_df.shape[1] < 3:
                    st.error("Mindestens 3 Spalten erforderlich (A–C).")
                else:
                    col_name, col_qty, col_price = raw_df.columns[:3]
                    rows = []
                    for _, r in raw_df.iterrows():
                        raw_name = str(r.get(col_name, "")).strip()
                        if not raw_name:
                            continue
                        name, unit_amount, unit = _parse_article_name(raw_name)
                        qty = 0.0 if zero_all else _to_float(r.get(col_qty))
                        price = _to_float(r.get(col_price))
                        grp = _guess_group(name) or ""
                        rows.append({
                            "name": name,
                            "unit_amount": unit_amount,
                            "unit": unit,
                            "stock_qty": qty,
                            "purchase_price": price,
                            "group": grp,
                        })

                    parsed_df = pd.DataFrame(rows, columns=["name", "unit_amount", "unit", "stock_qty", "purchase_price", "group"])
                    st.subheader("2) Vorschau & Bearbeitung")
                    st.caption("Du kannst die Felder direkt bearbeiten, inkl. Gruppe.")
                    edited = st.data_editor(
                        parsed_df,
                        use_container_width=True,
                        num_rows="dynamic",
                        column_config={
                            "name": st.column_config.TextColumn("Artikelname", required=True),
                            "unit_amount": st.column_config.NumberColumn("Menge", step=0.1, format="%.2f"),
                            "unit": st.column_config.SelectboxColumn("Einheit", options=["ml", "cl", "l", "", None], required=False),
                            "stock_qty": st.column_config.NumberColumn("Bestand (Stk.)", step=1, format="%.2f"),
                            "purchase_price": st.column_config.NumberColumn("EK netto (€)", step=0.01, format="%.2f"),
                            "group": st.column_config.SelectboxColumn("Gruppe", options=groups + [""], required=False),
                        }
                    )

                    if st.button("✅ Import / Aktualisieren (Upsert)", use_container_width=True):
                        ins, upd = 0, 0
                        for _, row in edited.iterrows():
                            data = {
                                "name": str(row["name"]).strip(),
                                "unit_amount": float(row["unit_amount"]) if pd.notna(row["unit_amount"]) else None,
                                "unit": (str(row["unit"]).lower() if pd.notna(row["unit"]) and row["unit"] else None),
                                "stock_qty": _to_float(row["stock_qty"]),
                                "purchase_price": _to_float(row["purchase_price"]),
                                "group": (str(row["group"]).strip().lower() if pd.notna(row["group"]) and row["group"] else None),
                            }
                            # gruppen, die neu sind, dynamisch ergänzen
                            if data.get("group") and data["group"] not in _get_groups():
                                _add_group(data["group"])

                            before_df = _fetch_items_df()
                            _upsert_item(data)
                            after_df = _fetch_items_df()
                            # naive Zählung: wenn neue ID auftauchte
                            if len(after_df) > len(before_df):
                                ins += 1
                            else:
                                upd += 1
                        st.success(f"Fertig: {ins} neu · {upd} aktualisiert.")
                        st.rerun()

    with right:
        st.subheader("Artikelgruppen")
        st.caption("Gruppen dienen der Strukturierung (z. B. „bier“, „wein“…).")
        existing = _get_groups()
        if existing:
            st.write("Vorhandene Gruppen:")
            st.markdown(", ".join([f"`{g}`" for g in existing]))
        else:
            st.info("Noch keine Gruppen vorhanden.")

        new_g = st.text_input("Neue Gruppe anlegen", placeholder="z. B. longdrinks")
        cols = st.columns([1,1])
        if cols[0].button("➕ Gruppe hinzufügen", use_container_width=True, disabled=not new_g.strip()):
            if _add_group(new_g.strip().lower()):
                st.success(f"Gruppe „{new_g}“ hinzugefügt.")
                st.rerun()
            else:
                st.error("Gruppe konnte nicht angelegt werden (existiert evtl. schon).")

        if existing:
            del_g = st.selectbox("Gruppe löschen", ["—"] + existing, index=0)
            if cols[1].button("🗑️ Gruppe löschen", use_container_width=True, disabled=(del_g=="—")):
                if _delete_group(del_g):
                    st.warning(f"Gruppe „{del_g}“ gelöscht.")
                    st.rerun()
                else:
                    st.error("Löschen fehlgeschlagen.")

    _divider()

    # ---------------------------------------------
    # Admin: bestehende Artikel filtern & bearbeiten
    # ---------------------------------------------
    st.subheader("📚 Bestehende Artikel (Datenbank)")
    groups_all = ["(alle)"] + _get_groups()
    gcol1, gcol2, gcol3 = st.columns([1, 2, 1])
    sel_group = gcol1.selectbox("Gruppe", groups_all, index=0)
    search = gcol2.text_input("Suche (Name enthält)…", "")
    show_zero = gcol3.checkbox("Nur Bestand = 0", value=False)

    df = _fetch_items_df()
    if sel_group != "(alle)":
        df = df[df["group"].fillna("") == sel_group]
    if search.strip():
        df = df[df["name"].str.contains(search.strip(), case=False, na=False)]
    if show_zero:
        df = df[(df["stock_qty"].fillna(0.0) == 0.0)]

    if df.empty:
        st.info("Keine passenden Datensätze.")
        return

    # Zusatzspalte für Delete-Flag
    df = df.copy()
    df["delete"] = False

    edited = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "name": st.column_config.TextColumn("Artikelname", required=True),
            "unit_amount": st.column_config.NumberColumn("Menge", step=0.1, format="%.2f"),
            "unit": st.column_config.SelectboxColumn("Einheit", options=["ml", "cl", "l", "", None]),
            "stock_qty": st.column_config.NumberColumn("Bestand (Stk.)", step=1, format="%.2f"),
            "purchase_price": st.column_config.NumberColumn("EK netto (€)", step=0.01, format="%.2f"),
            "group": st.column_config.SelectboxColumn("Gruppe", options=_get_groups() + [""], required=False),
            "last_updated": st.column_config.TextColumn("Zuletzt aktualisiert", disabled=True),
            "delete": st.column_config.CheckboxColumn("Löschen"),
        },
        hide_index=True,
    )

    a, b = st.columns([1,1])
    if a.button("💾 Änderungen speichern", use_container_width=True):
        try:
            del_ids: List[int] = []
            for _, r in edited.iterrows():
                if r.get("delete"):
                    del_ids.append(int(r["id"]))
                else:
                    itm = {
                        "id": int(r["id"]),
                        "name": str(r["name"]).strip(),
                        "unit_amount": float(r["unit_amount"]) if pd.notna(r["unit_amount"]) else None,
                        "unit": (str(r["unit"]).lower() if pd.notna(r["unit"]) and r["unit"] else None),
                        "stock_qty": _to_float(r["stock_qty"]),
                        "purchase_price": _to_float(r["purchase_price"]),
                        "group": (str(r["group"]).strip().lower() if pd.notna(r["group"]) and r["group"] else None),
                    }
                    # neue Gruppe ggf. anlegen
                    if itm.get("group") and itm["group"] not in _get_groups():
                        _add_group(itm["group"])
                    _update_item_by_id(itm)

            if del_ids:
                _delete_items_by_ids(del_ids)

            st.success("Änderungen gespeichert.")
            st.rerun()
        except Exception as e:
            st.error(f"Speichern fehlgeschlagen: {e}")

    if b.button("⬇️ CSV-Template herunterladen", use_container_width=True):
        tpl = pd.DataFrame({
            "Artikel (z.B. 'Coca Cola 0,2 l')": [],
            "Bestand": [],
            "EK Netto (€)": [],
            "Summe (optional)": [],
        })
        st.download_button(
            "CSV-Template",
            data=tpl.to_csv(index=False).encode("utf-8-sig"),
            file_name="artikel_template.csv",
            mime="text/csv",
        )
