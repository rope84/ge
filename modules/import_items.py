# modules/import_items.py
import re
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Tuple

import pandas as pd
import streamlit as st

from core.db import conn, DB_PATH, BACKUP_DIR

# ==========================
# DB: Ensure tables
# ==========================

def _table_exists(c, name: str) -> bool:
    return c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None

def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()

        # Items (mit created_at DEFAULT) + Unique-Index auf (name, unit_amount, unit)
        if not _table_exists(c, "items"):
            c.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                unit_amount REAL NOT NULL,
                unit TEXT NOT NULL,
                stock_qty REAL NOT NULL DEFAULT 0,
                purchase_price REAL NOT NULL DEFAULT 0,
                category_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
            """)
            c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_items_unique 
            ON items(name, unit_amount, unit)
            """)

        # Kategorien
        if not _table_exists(c, "categories"):
            c.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """)

        # Einfache Regel-Tabelle (Keyword → category_id)
        if not _table_exists(c, "category_rules"):
            c.execute("""
            CREATE TABLE IF NOT EXISTS category_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                keyword TEXT NOT NULL,
                UNIQUE(category_id, keyword),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
            """)

        cn.commit()

# ==========================
# Kategorien & Regeln
# ==========================

DEFAULT_CATEGORY_SETS = {
    "alkoholfrei": [
        "cola", "coca", "fanta", "sprite", "soda", "wasser",
        "ice tea", "icetea", "schorle", "juice", "saft",
    ],
    "bier": ["bier", "radler", "ipa", "stout", "lager", "pils", "weissbier", "helles"],
    "wein": ["wein", "riesling", "grüner veltliner", "merlot", "cabernet", "chardonnay"],
    "schaumwein": ["prosecco", "sekt", "champagner", "frizzante", "cava"],
}

def _get_categories() -> pd.DataFrame:
    with conn() as cn:
        return pd.read_sql("SELECT id, name FROM categories ORDER BY name", cn)

def _get_rules() -> pd.DataFrame:
    with conn() as cn:
        return pd.read_sql("""
            SELECT cr.id, cr.keyword, c.name AS category, cr.category_id
            FROM category_rules cr
            JOIN categories c ON c.id = cr.category_id
            ORDER BY c.name, cr.keyword
        """, cn)

def _ensure_default_categories_and_rules():
    with conn() as cn:
        c = cn.cursor()
        # Insert default categories if missing
        for cat, kws in DEFAULT_CATEGORY_SETS.items():
            c.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (cat,))
            # rules in next loop
        cn.commit()

    # insert default rules
    with conn() as cn:
        c = cn.cursor()
        for cat, kws in DEFAULT_CATEGORY_SETS.items():
            cat_id = c.execute("SELECT id FROM categories WHERE name=?", (cat,)).fetchone()
            if not cat_id:
                continue
            cat_id = cat_id[0]
            for kw in kws:
                c.execute("INSERT OR IGNORE INTO category_rules(category_id, keyword) VALUES(?, ?)", (cat_id, kw))
        cn.commit()

# ==========================
# Heuristik: Name → (unit_amount, unit, category)
# ==========================

_UNIT_PATTERNS = [
    # "0,2l", "0.2l", "0,33 l"
    (r"(\d+[,\.]?\d*)\s*l\b", 1.0, "l"),
    # "2cl", "4 cl"
    (r"(\d+[,\.]?\d*)\s*cl\b", 1.0, "cl"),
    # "1/8" oder "1/8l"
    (r"(\d+)\s*/\s*(\d+)\s*l?\b", None, "l"),  # später umrechnen
]

def _normalize_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None

def _extract_unit(name: str) -> Tuple[Optional[float], Optional[str]]:
    n = name.lower()
    # 1/8, 1/16 Beispiele
    m = re.search(_UNIT_PATTERNS[2][0], n)
    if m:
        a, b = m.group(1), m.group(2)
        try:
            val = float(a) / float(b)  # in Litern
            return (val, "l")
        except Exception:
            pass
    # Liter & cl
    for pat, factor, unit in _UNIT_PATTERNS[:2]:
        m = re.search(pat, n)
        if m:
            raw = _normalize_float(m.group(1))
            if raw is not None:
                return (raw * factor, unit)
    return (None, None)

def _auto_category(name: str) -> Optional[str]:
    n = name.lower()
    # durch Regeln (category_rules)
    rules = _get_rules()
    for _, row in rules.iterrows():
        if row["keyword"].lower() in n:
            return row["category"]

    # Fallback Heuristik
    if any(k in n for k in DEFAULT_CATEGORY_SETS["bier"]):
        return "bier"
    if any(k in n for k in DEFAULT_CATEGORY_SETS["schaumwein"]):
        return "schaumwein"
    if any(k in n for k in DEFAULT_CATEGORY_SETS["wein"]):
        return "wein"
    if any(k in n for k in DEFAULT_CATEGORY_SETS["alkoholfrei"]):
        return "alkoholfrei"
    return None

# ==========================
# Layout Helpers (Card)
# ==========================

def _card(title: str, body_md: str):
    st.markdown(
        f"""
        <div style="
            padding:14px 16px; border-radius:16px;
            background:rgba(255,255,255,0.03);
            box-shadow:0 8px 22px rgba(0,0,0,0.25);
            border:1px solid rgba(255,255,255,0.06);
            margin-bottom:12px;
        ">
            <div style="font-weight:600; margin-bottom:8px;">{title}</div>
            <div style="opacity:0.95;">{body_md}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ==========================
# Persist helpers
# ==========================

def _get_category_id_by_name(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

def _upsert_item(row: dict):
    """Upsert per (name, unit_amount, unit)."""
    with conn() as cn:
        c = cn.cursor()
        # resolve category
        cat_id = _get_category_id_by_name(row.get("category"))
        # try update
        c.execute("""
            UPDATE items
            SET stock_qty = ?, purchase_price = ?, category_id = ?
            WHERE name=? AND unit_amount=? AND unit=?
        """, (
            float(row.get("stock_qty") or 0),
            float(row.get("purchase_price") or 0),
            cat_id,
            row["name"],
            float(row["unit_amount"]),
            row["unit"]
        ))
        if c.rowcount == 0:
            c.execute("""
                INSERT INTO items(name, unit_amount, unit, stock_qty, purchase_price, category_id)
                VALUES(?,?,?,?,?,?)
            """, (
                row["name"],
                float(row["unit_amount"]),
                row["unit"],
                float(row.get("stock_qty") or 0),
                float(row.get("purchase_price") or 0),
                cat_id
            ))
        cn.commit()

# ==========================
# UI: Kategorien-Tab
# ==========================

def _render_categories_tab():
    _ensure_tables()
    _ensure_default_categories_and_rules()

    st.subheader("Kategorien verwalten")

    # Add / edit categories
    with st.form("cat_add"):
        c1, c2 = st.columns([2,1])
        new_cat = c1.text_input("Neue Kategorie", placeholder="z.B. alkoholfrei")
        submitted = c2.form_submit_button("➕ Anlegen", use_container_width=True)
        if submitted and new_cat.strip():
            try:
                with conn() as cn:
                    cn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (new_cat.strip().lower(),))
                    cn.commit()
                st.success(f"Kategorie '{new_cat}' angelegt.")
            except Exception as e:
                st.error(f"Fehler: {e}")

    cats = _get_categories()
    if cats.empty:
        st.info("Noch keine Kategorien.")
    else:
        for _, crow in cats.iterrows():
            with st.expander(f"🗂️ {crow['name']}", expanded=False):
                col1, col2 = st.columns([3,1])
                new_name = col1.text_input("Name ändern", value=crow["name"], key=f"cat_name_{crow['id']}")
                if col2.button("💾 Speichern", key=f"cat_save_{crow['id']}", use_container_width=True):
                    try:
                        with conn() as cn:
                            cn.execute("UPDATE categories SET name=? WHERE id=?", (new_name.strip().lower(), crow["id"]))
                            cn.commit()
                        st.success("Gespeichert.")
                    except Exception as e:
                        st.error(f"Fehler: {e}")

                st.markdown("**Regeln (Keywords)** – Wenn eines dieser Wörter im Artikelnamen vorkommt, wird die Kategorie automatisch gesetzt.")
                # List existing rules
                rules = _get_rules()
                rules = rules[rules["category_id"] == crow["id"]]
                if rules.empty:
                    st.caption("Noch keine Keywords für diese Kategorie.")
                else:
                    for _, rrow in rules.iterrows():
                        rcol1, rcol2 = st.columns([3,1])
                        st.text_input("Keyword", value=rrow["keyword"], disabled=True, key=f"kw_show_{rrow['id']}")
                        if rcol2.button("🗑️ Entfernen", key=f"kw_del_{rrow['id']}", use_container_width=True):
                            try:
                                with conn() as cn:
                                    cn.execute("DELETE FROM category_rules WHERE id=?", (rrow["id"],))
                                    cn.commit()
                                st.success("Keyword entfernt.")
                                st.experimental_rerun()
                            except Exception as e:
                                st.error(f"Fehler: {e}")

                # Add new keyword
                with st.form(f"kw_add_{crow['id']}"):
                    k1, k2 = st.columns([3,1])
                    new_kw = k1.text_input("Neues Keyword", placeholder="z.B. cola")
                    add_kw = k2.form_submit_button("➕ Hinzufügen", use_container_width=True)
                    if add_kw and new_kw.strip():
                        try:
                            with conn() as cn:
                                cn.execute(
                                    "INSERT OR IGNORE INTO category_rules(category_id, keyword) VALUES(?, ?)",
                                    (crow["id"], new_kw.strip().lower())
                                )
                                cn.commit()
                            st.success("Keyword hinzugefügt.")
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Fehler: {e}")

                dcol1, dcol2 = st.columns([3,1])
                if dcol2.button("Kategorie löschen", key=f"cat_del_{crow['id']}", use_container_width=True):
                    try:
                        with conn() as cn:
                            cn.execute("DELETE FROM category_rules WHERE category_id=?", (crow["id"],))
                            cn.execute("UPDATE items SET category_id=NULL WHERE category_id=?", (crow["id"],))
                            cn.execute("DELETE FROM categories WHERE id=?", (crow["id"],))
                            cn.commit()
                        st.warning("Kategorie gelöscht.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Fehler: {e}")

    st.markdown("---")
    # Batch-Reklassifizierung (DB)
    if st.button("🔁 Alle bestehenden Artikel in der Datenbank neu klassifizieren", use_container_width=True):
        try:
            with conn() as cn:
                c = cn.cursor()
                rows = c.execute("SELECT id, name FROM items").fetchall()
                for iid, nm in rows:
                    cat = _auto_category(nm)  # by rules + fallback
                    if cat:
                        cat_id = _get_category_id_by_name(cat)
                        if cat_id:
                            c.execute("UPDATE items SET category_id=? WHERE id=?", (cat_id, iid))
                cn.commit()
            st.success("Reklassifizierung abgeschlossen.")
        except Exception as e:
            st.error(f"Fehler: {e}")

# ==========================
# UI: Import-Workflow Tab
# ==========================

REQUIRED_COLUMNS = ["Artikel", "Einheit", "Menge", "Einkaufspreis"]

def _parse_unit(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Map '0,2l', '2cl', '1/8' → (amount, unit)"""
    if not text:
        return (None, None)
    # Versuche direkt aus 'Einheit' zu lesen
    amt, unit = _extract_unit(text)
    return (amt, unit)

def _split_unit_field(unit_field: str) -> Tuple[Optional[float], Optional[str]]:
    """Falls 'Einheit' Spalte frei formatiert ist ('0,2l' oder '2 cl' etc.)."""
    return _parse_unit(unit_field)

def _auto_map_row(row: dict) -> dict:
    """Map Excel-Zeile auf internes Schema."""
    name = str(row.get("Artikel", "")).strip()
    unit_field = str(row.get("Einheit", "")).strip()

    # Einheit
    amount, unit = _split_unit_field(unit_field)
    if amount is None or unit is None:
        # versuche aus dem Namen zu parsen
        amount, unit = _extract_unit(name)

    # Standard: wenn nichts gefunden, auf Liter defaulten (0.2l)
    if amount is None and unit is None:
        amount, unit = (0.2, "l")

    # Mengen / Preis
    try:
        stock_qty = float(str(row.get("Menge", 0)).replace(",", "."))
    except Exception:
        stock_qty = 0.0

    try:
        purchase_price = float(str(row.get("Einkaufspreis", 0)).replace(",", "."))
    except Exception:
        purchase_price = 0.0

    # Kategorie anhand Regeln/Heuristik
    cat = _auto_category(name) or ""

    return {
        "name": name,
        "unit_amount": amount or 0.0,
        "unit": unit or "l",
        "stock_qty": stock_qty,
        "purchase_price": purchase_price,
        "category": cat,
    }

def _render_import_tab():
    _ensure_tables()
    _ensure_default_categories_and_rules()

    st.subheader("Artikel importieren (Excel)")

    _card(
        "Format",
        """
        Erwartete Spalten: **Artikel**, **Einheit** (z. B. `0,2l`, `2cl`, `1/8`), **Menge** (Inventurstand),
        **Einkaufspreis** (Netto).<br/>
        Tipp: Wir erkennen Einheiten auch aus dem Artikelnamen (z. B. *\"Coca Cola 0,2l\"*).
        """
    )

    file = st.file_uploader("Excel auswählen", type=["xlsx", "xls"])
    if file:
        try:
            df = pd.read_excel(file)
        except Exception as e:
            st.error(f"Excel konnte nicht gelesen werden: {e}")
            return

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            st.error(f"Folgende Spalten fehlen: {', '.join(missing)}")
            return

        # Vorschau-Mapping
        mapped_rows = [_auto_map_row(rec) for rec in df.to_dict("records")]
        preview = pd.DataFrame(mapped_rows)

        # Nutzer kann alles in schöner Editor-UI anpassen
        cats = _get_categories()
        cat_names = [""] + sorted(cats["name"].tolist()) if not cats.empty else [""]

        st.markdown("### Vorschau & Bearbeitung")
        st.caption("Passe Werte an (Einheit, Mengen, Kategorie). Einheit = Menge + Einheit z. B. 0.2 + l oder 2 + cl.")

        # Data Editor Konfiguration
        edited = st.data_editor(
            preview,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "name": st.column_config.TextColumn("Artikel", help="Artikelbezeichnung"),
                "unit_amount": st.column_config.NumberColumn("Menge (Einheit)", help="z. B. 0.2 für 0,2l oder 2 für 2cl", step=0.01),
                "unit": st.column_config.SelectboxColumn("Einheit", options=["l", "cl"], help="Einheit (l oder cl)"),
                "stock_qty": st.column_config.NumberColumn("Inventurstand (Stk.)", step=1.0),
                "purchase_price": st.column_config.NumberColumn("Einkaufspreis (Netto)", step=0.01, format="%.2f"),
                "category": st.column_config.SelectboxColumn("Kategorie", options=cat_names),
            },
        )

        col_l, col_r = st.columns([1,1])
        reclass = col_l.button("🔁 Kategorien automatisch setzen (Regeln anwenden)")
        if reclass:
            # wende Auto-Kategorie neu an
            edited["category"] = edited["name"].apply(lambda n: _auto_category(n) or edited["category"])
            st.experimental_rerun()

        proceed = col_r.button("Weiter ➜", use_container_width=True)
        if proceed:
            st.session_state["items_preview"] = edited
            st.session_state["items_preview_time"] = datetime.datetime.now().isoformat()
            st.success("Vorschau gespeichert. Scrolle weiter zu 'Final speichern'.")
            st.experimental_rerun()

        st.markdown("---")

        # Finalisierungs-Box (nur wenn es eine Preview gibt)
        if "items_preview" in st.session_state:
            _card(
                "Final speichern",
                """
                Prüfe deine Änderungen – mit **„Jetzt in Datenbank speichern“** werden die Artikel
                per *Upsert* (Name + Einheit) importiert/aktualisiert. 
                """
            )
            save = st.button("✅ Jetzt in Datenbank speichern", type="primary", use_container_width=True)
            if save:
                try:
                    pv = st.session_state["items_preview"].to_dict("records")
                    for row in pv:
                        # Leere Kategorie als None
                        if not row.get("category"):
                            row["category"] = None
                        _upsert_item(row)
                    st.success("Artikel erfolgreich gespeichert.")
                    del st.session_state["items_preview"]
                    del st.session_state["items_preview_time"]
                except Exception as e:
                    st.error(f"Fehler beim Speichern: {e}")

    else:
        _card("Hinweis", "Bitte eine Excel-Datei hochladen, um die Vorschau zu starten.")

# ==========================
# Entry: Render in Admin
# ==========================

def render_data_tools():
    """Wird aus admin.py im Tab '📦 Daten' aufgerufen."""
    _ensure_tables()
    _ensure_default_categories_and_rules()

    tabs = st.tabs(["📥 Artikel importieren", "🗂️ Kategorien"])
    with tabs[0]:
        _render_import_tab()
    with tabs[1]:
        _render_categories_tab()
