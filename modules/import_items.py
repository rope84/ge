# modules/import_items.py
import re
import datetime
import pandas as pd
import streamlit as st
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from core.db import conn

# ----------------------------
# DB Schema (nur falls nicht vorhanden)
# ----------------------------
def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()

        # Artikel-Stammdaten (eigenständig, kollidiert nicht mit deinen bisherigen Tabellen)
        c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            unit_amount REAL,
            unit TEXT,
            net_price REAL NOT NULL DEFAULT 0,
            stock_qty REAL NOT NULL DEFAULT 0,
            total_value REAL NOT NULL DEFAULT 0,
            category TEXT,
            pack TEXT,
            sku TEXT,
            created_at TEXT NOT NULL
        )
        """)

        # Eindeutigkeit: (name, unit_amount, unit)
        c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_items_unique
        ON items(name, unit_amount, unit)
        """)

        # Kategorie-Liste (optional, frei editierbar)
        c.execute("""
        CREATE TABLE IF NOT EXISTS item_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT
        )
        """)
        cn.commit()


# ----------------------------
# Utils
# ----------------------------
_DECIMAL_COMMA = re.compile(r"(\d+),(\d+)")
_SIZE_RE = re.compile(r"(?P<amount>\d+[.,]?\d*)\s*(?P<unit>cl|l|ml|g|kg|stk|stk\.?)$", re.IGNORECASE)

def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(" ", "")
    s = _DECIMAL_COMMA.sub(r"\1.\2", s)  # 0,2 -> 0.2
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def _parse_size(text: str) -> Tuple[Optional[float], Optional[str]]:
    if not text:
        return None, None
    m = _SIZE_RE.search(text.strip())
    if not m:
        return None, None
    amt = _to_float(m.group("amount"))
    unit = m.group("unit").lower().replace("stk.", "stk")
    return amt, unit

def _guess_category(name: str) -> Optional[str]:
    n = (name or "").strip().lower()
    if not n:
        return None
    if any(k in n for k in ["wasser", "cola", "sprite", "fanta", "eistee", "saft", "juice", "tonic", "red bull", "schorle", "limo", "limonade", "alkoholfrei"]):
        return "Alkoholfrei"
    if any(k in n for k in ["bier", "radler", "ipa", "stout", "pils", "lager", "weizen"]):
        return "Bier"
    if any(k in n for k in ["prosecco", "sekt", "cava", "champagner", "schaumwein", "frizzante"]):
        return "Schaumwein"
    if any(k in n for k in ["riesling", "veltliner", "zweigelt", "merlot", "sauvignon", "wein", "blaufränkisch", "chardonnay"]):
        return "Wein"
    if any(k in n for k in ["gin", "vodka", "rum", "tequila", "whisky", "whiskey", "bourbon", "cognac", "brandy"]):
        return "Spirituose"
    return None

def _load_categories() -> List[Dict]:
    with conn() as cn:
        df = pd.read_sql("SELECT id, name, color FROM item_categories ORDER BY name", cn)
    return df.to_dict(orient="records")

def _ensure_category(name: str, color: Optional[str] = None):
    if not name:
        return
    with conn() as cn:
        c = cn.cursor()
        try:
            c.execute("INSERT OR IGNORE INTO item_categories(name, color) VALUES(?,?)", (name, color or None))
            cn.commit()
        except Exception:
            pass

def _upsert_item(row: Dict):
    """
    row: dict with keys: name, unit_amount, unit, net_price, stock_qty, total_value, category, pack, sku
    UPSERT via unique index (name, unit_amount, unit)
    """
    with conn() as cn:
        c = cn.cursor()
        now = datetime.datetime.now().isoformat(timespec="seconds")
        # existiert?
        cur = c.execute(
            "SELECT id FROM items WHERE name=? AND (unit_amount IS ? OR unit_amount=?) AND (unit IS ? OR unit=?)",
            (row.get("name"),
             row.get("unit_amount"), row.get("unit_amount"),
             row.get("unit"), row.get("unit"))
        ).fetchone()
        total_value = float(row.get("stock_qty") or 0) * float(row.get("net_price") or 0)
        if cur:
            c.execute("""
                UPDATE items
                   SET net_price=?,
                       stock_qty=?,
                       total_value=?,
                       category=?,
                       pack=?,
                       sku=? 
                 WHERE id=?
            """, (row.get("net_price") or 0,
                  row.get("stock_qty") or 0,
                  total_value,
                  row.get("category"),
                  row.get("pack"),
                  row.get("sku"),
                  cur[0]))
        else:
            c.execute("""
                INSERT INTO items(name, unit_amount, unit, net_price, stock_qty, total_value, category, pack, sku, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (row.get("name"),
                  row.get("unit_amount"),
                  row.get("unit"),
                  row.get("net_price") or 0,
                  row.get("stock_qty") or 0,
                  total_value,
                  row.get("category"),
                  row.get("pack"),
                  row.get("sku"),
                  now))
        cn.commit()


# ----------------------------
# MAPPING UI & PARSER
# ----------------------------
EXPECTED = {
    "name": "Artikelname",
    "size": "Menge/Einheit (z.B. 0,2l oder 2cl) – optional",
    "stock_qty": "Bestand / letzter Inventurstand (Stk)",
    "net_price": "Netto-Einkaufspreis pro Einheit (€)",
    # optional:
    "pack": "Gebinde/Packung (optional)",
    "sku": "SKU/Artikelnummer (optional)"
}

def _clean_uploaded_df(df: pd.DataFrame) -> pd.DataFrame:
    # Spaltennamen säubern
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    # leere Zeilen entfernen
    df = df.dropna(how="all")
    # Strings trimmen
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
    return df

def _apply_mapping(raw_df: pd.DataFrame, mapping: Dict[str, Optional[str]]) -> pd.DataFrame:
    """
    mapping keys in EXPECTED; values = Spaltenname aus raw_df (oder None)
    """
    out = pd.DataFrame()
    # Name (Pflicht)
    out["name"] = raw_df[mapping["name"]].astype(str).str.strip()

    # Größe: versuche aus zugeordneter Spalte zu lesen, sonst versuche direkt aus name zu parsen
    amt = []
    unt = []
    if mapping.get("size") and mapping["size"] in raw_df.columns:
        for s in raw_df[mapping["size"]].astype(str).fillna(""):
            a, u = _parse_size(s)
            amt.append(a)
            unt.append(u)
    else:
        # versuche am Ende des Namens zu erkennen (zB "Tonic 0,2l")
        for n in out["name"]:
            a, u = _parse_size(n)
            amt.append(a)
            unt.append(u)
    out["unit_amount"] = amt
    out["unit"] = [u.lower() if u else None for u in unt]

    # Bestand / Preis (Pflichtfelder dürfen 0 sein)
    out["stock_qty"] = raw_df[mapping["stock_qty"]].apply(_to_float) if mapping.get("stock_qty") else 0.0
    out["net_price"]  = raw_df[mapping["net_price"]].apply(_to_float)  if mapping.get("net_price")  else 0.0

    # Optional
    out["pack"] = raw_df[mapping["pack"]].astype(str) if mapping.get("pack") and mapping["pack"] in raw_df.columns else ""
    out["sku"]  = raw_df[mapping["sku"]].astype(str)  if mapping.get("sku")  and mapping["sku"]  in raw_df.columns else ""

    # Total
    out["total_value"] = out["stock_qty"].fillna(0) * out["net_price"].fillna(0)

    # Kategorie vorschlagen
    out["category"] = out["name"].apply(_guess_category)

    # Anzeige-Helfer
    return out


# ----------------------------
# UI
# ----------------------------
def render_import_items():
    _ensure_tables()

    st.markdown("### 📥 Artikelimport (Excel/CSV)")
    st.caption("Lade deine Artikelliste hoch, ordne Spalten zu, korrigiere Werte inline & speichere direkt in die Datenbank.")

    tabs = st.tabs(["1) Upload", "2) Prüfen & Bearbeiten", "3) Speichern"])

    # --- Sidebar: Kategorien verwalten ---
    with st.sidebar:
        st.markdown("#### 🏷️ Kategorien verwalten")
        cats = _load_categories()
        if cats:
            for c in cats:
                color = c.get("color") or "#6b7280"
                st.markdown(
                    f"<div style='display:inline-block;margin:2px;padding:2px 8px;border-radius:999px;"
                    f"background:{color}22;color:{color};border:1px solid {color}55;font-size:12px'>{c['name']}</div>",
                    unsafe_allow_html=True
                )
        with st.form("cat_add"):
            st.write("")
            new_cat = st.text_input("Neue Kategorie")
            new_col = st.color_picker("Farbe", value="#3b82f6")
            if st.form_submit_button("➕ Kategorie anlegen", use_container_width=True):
                if new_cat.strip():
                    _ensure_category(new_cat.strip(), new_col)
                    st.experimental_rerun()

    # --- Tab 1: Upload ---
    with tabs[0]:
        up = st.file_uploader("Excel (.xlsx) oder CSV hochladen", type=["xlsx", "csv"])
        if up:
            if up.name.lower().endswith(".xlsx"):
                raw_df = pd.read_excel(up)
            else:
                raw_df = pd.read_csv(up, sep=None, engine="python")

            raw_df = _clean_uploaded_df(raw_df)
            st.success(f"✅ Datei geladen: {up.name} – {len(raw_df)} Zeilen")
            st.dataframe(raw_df.head(15), use_container_width=True, height=280)
            st.session_state["import_raw_df"] = raw_df
        else:
            st.info("Bitte Datei hochladen.")

    # --- Tab 2: Prüfen & Bearbeiten ---
    with tabs[1]:
        raw_df: Optional[pd.DataFrame] = st.session_state.get("import_raw_df")
        if raw_df is None:
            st.warning("Bitte zuerst eine Datei im Tab **Upload** laden.")
        else:
            st.subheader("Spaltenzuordnung")
            cols = ["(Bitte wählen)"] + list(raw_df.columns)
            def pick(label, default=None):
                return st.selectbox(label, cols, index=(cols.index(default) if default in cols else 0))

            # sinnvolle Defaults raten
            guess_name = next((c for c in raw_df.columns if str(c).lower() in ["artikel", "name", "produkt", "bezeichnung"]), None)
            guess_size = next((c for c in raw_df.columns if "menge" in str(c).lower() or "einheit" in str(c).lower()), None)
            guess_qty  = next((c for c in raw_df.columns if "stand" in str(c).lower() or "bestand" in str(c).lower()), None)
            guess_price= next((c for c in raw_df.columns if "preis" in str(c).lower() or "einkauf" in str(c).lower()), None)

            m_name = pick("Artikelname *", guess_name)
            m_size = pick("Menge/Einheit (z.B. 0,2l) – optional", guess_size)
            m_qty  = pick("Bestand / Inventurstand (Stk) *", guess_qty)
            m_prc  = pick("Netto-Einkaufspreis (€) *", guess_price)
            m_pack = pick("Gebinde/Packung (optional)")
            m_sku  = pick("SKU/Artikelnummer (optional)")

            if st.button("🔁 Vorschau aktualisieren", use_container_width=True, key="refresh_preview"):
                st.session_state["import_mapped_df"] = _apply_mapping(raw_df, {
                    "name": m_name if m_name != "(Bitte wählen)" else None,
                    "size": m_size if m_size != "(Bitte wählen)" else None,
                    "stock_qty": m_qty if m_qty != "(Bitte wählen)" else None,
                    "net_price": m_prc if m_prc != "(Bitte wählen)" else None,
                    "pack": m_pack if m_pack != "(Bitte wählen)" else None,
                    "sku": m_sku  if m_sku  != "(Bitte wählen)" else None,
                })

            mapped_df: Optional[pd.DataFrame] = st.session_state.get("import_mapped_df")
            if mapped_df is not None:
                st.markdown("##### Vorschau & Inline-Bearbeitung")
                # Kategorien-Liste für Dropdown
                cat_names = [c["name"] for c in _load_categories()]
                cfg = {
                    "name": st.column_config.TextColumn("Artikel"),
                    "unit_amount": st.column_config.NumberColumn("Menge", step=0.1, format="%.2f"),
                    "unit": st.column_config.TextColumn("Einheit"),
                    "net_price": st.column_config.NumberColumn("Einkauf (€)", step=0.01, format="%.2f", help="Netto pro Einheit"),
                    "stock_qty": st.column_config.NumberColumn("Bestand (Stk)", step=1, format="%.0f", help="Letzter Inventurstand (darf 0 sein)"),
                    "total_value": st.column_config.NumberColumn("Wert gesamt (€)", disabled=True, format="%.2f"),
                    "category": st.column_config.SelectboxColumn("Kategorie", options=cat_names or ["—"], help="Wähle oder lege links im Sidebar neue Kategorien an."),
                    "pack": st.column_config.TextColumn("Gebinde"),
                    "sku": st.column_config.TextColumn("SKU"),
                }
                edit_df = st.data_editor(
                    mapped_df,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    column_config=cfg,
                    key="editor_items_grid",
                    height=420,
                )
                # Total on the fly zeigen
                tot = float((edit_df["stock_qty"].fillna(0) * edit_df["net_price"].fillna(0)).sum())
                st.caption(f"Gesamt-Warenwert dieser Auswahl: **{tot:,.2f} €**")

                st.session_state["import_edit_df"] = edit_df
            else:
                st.info("Mappe die Spalten und klicke **Vorschau aktualisieren**.")

    # --- Tab 3: Speichern ---
    with tabs[2]:
        edit_df: Optional[pd.DataFrame] = st.session_state.get("import_edit_df")
        if edit_df is None or edit_df.empty:
            st.warning("Bitte zuerst im Tab **Prüfen & Bearbeiten** eine Vorschau erzeugen.")
        else:
            st.success(f"Bereit zum Speichern: {len(edit_df)} Artikel")
            col_a, col_b = st.columns([1, 1])
            only_new = col_a.checkbox("Nur neue Artikel anlegen (bestehende unverändert lassen)", value=False)
            normalize  = col_b.checkbox("Einheiten normalisieren (ml→l, g→kg wenn sinnvoll)", value=True)

            if st.button("💾 Alles speichern", use_container_width=True, key="save_items_now"):
                # Normalisierung
                df_to_save = edit_df.copy()
                if normalize:
                    # ml → l
                    mask_ml = df_to_save["unit"].str.lower().eq("ml")
                    df_to_save.loc[mask_ml, "unit_amount"] = df_to_save.loc[mask_ml, "unit_amount"].astype(float) / 1000.0
                    df_to_save.loc[mask_ml, "unit"] = "l"
                    # g → kg
                    mask_g = df_to_save["unit"].str.lower().eq("g")
                    df_to_save.loc[mask_g, "unit_amount"] = df_to_save.loc[mask_g, "unit_amount"].astype(float) / 1000.0
                    df_to_save.loc[mask_g, "unit"] = "kg"

                # Speichern (UPSERT)
                saved, skipped = 0, 0
                for _, r in df_to_save.iterrows():
                    # Kategorie ggf. erzeugen
                    if r.get("category"):
                        _ensure_category(str(r["category"]).strip())

                    payload = {
                        "name": str(r.get("name") or "").strip(),
                        "unit_amount": _to_float(r.get("unit_amount")),
                        "unit": (str(r.get("unit") or "").strip().lower() or None),
                        "net_price": _to_float(r.get("net_price")) or 0.0,
                        "stock_qty": _to_float(r.get("stock_qty")) or 0.0,
                        "category": (str(r.get("category") or "").strip() or None),
                        "pack": (str(r.get("pack") or "").strip() or None),
                        "sku": (str(r.get("sku") or "").strip() or None),
                    }
                    if not payload["name"]:
                        continue

                    if only_new:
                        # existiert?
                        with conn() as cn:
                            c = cn.cursor()
                            cur = c.execute(
                                "SELECT 1 FROM items WHERE name=? AND (unit_amount IS ? OR unit_amount=?) AND (unit IS ? OR unit=?)",
                                (payload["name"], payload["unit_amount"], payload["unit_amount"], payload["unit"], payload["unit"])
                            ).fetchone()
                        if cur:
                            skipped += 1
                            continue

                    _upsert_item(payload)
                    saved += 1

                st.success(f"Fertig: {saved} Artikel gespeichert, {skipped} übersprungen.")
                # Aufräumen (optional)
                # del st.session_state["import_raw_df"]
                # del st.session_state["import_mapped_df"]
                # del st.session_state["import_edit_df"]

    st.markdown("---")
    st.caption("Tipp: Für beste Ergebnisse verwende Spalten: **Artikel**, **Bestand**, **Einkaufspreis** und optional **Menge/Einheit** (z. B. `0,2l`).")
