import streamlit as st
import pandas as pd
import re
import json
import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from core.db import conn
from core.ui_theme import section_title

# ---------------------- DB: items & Kategorien (meta) ----------------------

def _ensure_items_table():
    with conn() as cn:
        c = cn.cursor()
        # Basis-Tabelle (nur falls noch nicht da)
        c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            unit_amount REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT '',
            stock_qty REAL NOT NULL DEFAULT 0,
            purchase_price REAL NOT NULL DEFAULT 0,
            category TEXT,
            created_at TEXT
        )
        """)
        # Spalten prüfen (Migration alter Schemas)
        c.execute("PRAGMA table_info(items)")
        cols = {row[1] for row in c.fetchall()}

        expected = {
            "name":           "TEXT NOT NULL",
            "unit_amount":    "REAL NOT NULL DEFAULT 0",
            "unit":           "TEXT NOT NULL DEFAULT ''",
            "stock_qty":      "REAL NOT NULL DEFAULT 0",
            "purchase_price": "REAL NOT NULL DEFAULT 0",
            "category":       "TEXT",
            # created_at OHNE NOT NULL, wir setzen es aktiv beim Insert/Update
            "created_at":     "TEXT"
        }
        for col, decl in expected.items():
            if col not in cols:
                c.execute(f"ALTER TABLE items ADD COLUMN {col} {decl}")

        # vorhandene NULL/leer bei created_at auffüllen
        c.execute("UPDATE items SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''")

        # Eindeutigkeit
        c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_items_unique
        ON items(name, unit_amount, unit)
        """)

        # Kategorien-Store in meta
        c.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        have = c.execute("SELECT value FROM meta WHERE key='item_categories'").fetchone()
        if not have:
            default = [
                {"name": "Alkoholfrei", "keywords": ["cola","fanta","sprite","wasser","soda","saft","energydrink","juice","tonic"]},
                {"name": "Bier", "keywords": ["bier","radler","ipa","stout","pils","weissbier","weizen"]},
                {"name": "Wein", "keywords": ["wein","rotwein","weißwein","weisswein","grüner","veltliner","merlot","zweigelt","riesling"]},
                {"name": "Schaumwein", "keywords": ["prosecco","sekt","champagner","frizzante"]},
                {"name": "Spirituosen", "keywords": ["vodka","gin","rum","tequila","whisky","whiskey","likör","brandy","cognac"]},
            ]
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('item_categories', ?)", (json.dumps(default, ensure_ascii=False),))
        cn.commit()

def _get_categories() -> List[Dict]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT value FROM meta WHERE key='item_categories'").fetchone()
        if not row or not row[0]:
            return []
        try:
            return json.loads(row[0])
        except Exception:
            return []

def _save_categories(cats: List[Dict]):
    with conn() as cn:
        c = cn.cursor()
        c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('item_categories', ?)", (json.dumps(cats, ensure_ascii=False),))
        cn.commit()

# ---------------------- Header-Mapping & Parsing ----------------------

# Synonyme für Spalten-Erkennung
SYNONYMS = {
    "name": ["artikel","produkt","bezeichnung","item","name","artikelname","produktname","titel"],
    "unit": ["einheit","unit","maßeinheit","measure","uom"],
    "stock_qty": ["menge","stand","anzahl","bestand","qty","quantity","lager","inventur"],
    "purchase_price": ["einkaufspreis","ek","netto","purchase","price","nettopreis","preis (netto)","netto preis"],
    "category": ["kategorie","warengruppe","artikelgruppe","gruppe","category"],
}

def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.strip().lower())

def _guess_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    mapping = {k: None for k in ["name","unit","stock_qty","purchase_price","category"]}
    norm_cols = {col: _normalize(col) for col in df.columns}
    for logical, syns in SYNONYMS.items():
        for col, n in norm_cols.items():
            if n in [_normalize(x) for x in syns]:
                mapping[logical] = col
                break
    # Minimal: Name muss irgendwie gefunden werden – fallback: erste Spalte
    if mapping["name"] is None and len(df.columns) > 0:
        mapping["name"] = list(df.columns)[0]
    return mapping

# Einheit-Parsing: z. B. "Coca Cola 0,2l", "Soda 1/8", "Wasser 500ml"
_FRACTIONS = {
    "1/16": 1.0/16.0,
    "1/8": 1.0/8.0,
    "1/4": 0.25,
    "1/2": 0.5,
}

def _parse_unit_from_name(name: str) -> Tuple[str, float, str]:
    """
    Liefert (clean_name, unit_amount, unit).
    Erkennt Muster wie:
      - "0,2l" / "0.2 l" / "500ml"
      - "2cl", "4 cl"
      - "1/8", "1/4" -> Liter
    Entfernt die Einheitsangabe aus dem Namen.
    """
    raw = name
    n = name.strip()

    # Fraktionen (1/8, 1/4, ...)
    m = re.search(r'(\b1/16\b|\b1/8\b|\b1/4\b|\b1/2\b)', n, flags=re.IGNORECASE)
    if m:
        frac = m.group(1)
        amt = _FRACTIONS[frac.lower()]
        clean = re.sub(re.escape(frac), "", n, flags=re.IGNORECASE).strip(" -–()")
        return (clean.strip(), float(amt), "l")

    # Klassisch: Zahl + Einheit
    # Beispiele: "0,2l", "0.33 l", "500ml", "4 cl"
    m = re.search(r'(\d+[.,]?\d*)\s*(l|cl|ml)\b', n, flags=re.IGNORECASE)
    if m:
        num = m.group(1).replace(",", ".")
        unit = m.group(2).lower()
        try:
            val = float(num)
        except Exception:
            val = 0.0

        # ml->l, cl->l normalisieren
        if unit == "ml":
            amt = val / 1000.0
            unit_out = "l"
        elif unit == "cl":
            amt = val / 100.0
            unit_out = "l"
        else:
            amt = val
            unit_out = "l"

        clean = re.sub(re.escape(m.group(0)), "", n, flags=re.IGNORECASE).strip(" -–()")
        return (clean.strip(), float(amt), unit_out)

    # nichts gefunden -> 0 l
    return (raw.strip(), 0.0, "")

def _auto_category(name: str, cats: List[Dict]) -> Optional[str]:
    n = _normalize(name)
    best = None
    for cat in cats:
        kws = cat.get("keywords", [])
        for kw in kws:
            if _normalize(kw) and _normalize(kw) in n:
                best = cat.get("name")
                break
        if best:
            break
    return best

# ---------------------- Workflow State ----------------------

def _get_state():
    s = st.session_state
    s.setdefault("imp_raw_df", None)
    s.setdefault("imp_mapping", None)
    s.setdefault("imp_clean_df", None)
    s.setdefault("imp_step", 1)  # 1 Upload/Mapping, 2 Prüfen/Bearbeiten, 3 Speichern
    return s

# ---------------------- UI: Karten/Boxen ----------------------

def _box(title: str, body_md: str):
    st.markdown(
        f"""
        <div style="
            padding:14px 16px; border-radius:14px;
            background:rgba(255,255,255,0.03);
            box-shadow:0 6px 16px rgba(0,0,0,0.20);
            border:1px solid rgba(255,255,255,0.06);
            ">
            <div style="font-weight:600; margin-bottom:6px;">{title}</div>
            <div style="font-size:13px; opacity:0.95;">{body_md}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------------------- Schritt 1: Upload & Mapping ----------------------

def _step_upload_and_map():
    section_title("📥 Artikel-Import – Datei hochladen & Spalten zuordnen")

    hint = """
    **Erwartete Felder (logisch):**
    - Artikel **(Pflicht)** – z. B. *Coca Cola 0,2l*  
    - Einheit *(optional)* – wenn nicht vorhanden, wird aus dem Namen geparst  
    - Menge *(optional)* – Lager/Inventurstand; Standard = 0  
    - Einkaufspreis *(optional)* – Netto EK; Standard = 0  
    - Kategorie *(optional)* – z. B. *Alkoholfrei*, *Bier*, *Wein* …
    """
    _box("Hinweis", hint)

    file = st.file_uploader("Excel oder CSV auswählen", type=["xlsx","xls","csv"])
    if not file:
        return None, None

    # Lesen
    try:
        if file.name.lower().endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
    except Exception as e:
        st.error(f"Datei konnte nicht gelesen werden: {e}")
        return None, None

    if df.empty:
        st.warning("Die Datei ist leer.")
        return None, None

    st.success(f"Datei geladen: {file.name} – {len(df)} Zeile(n), {len(df.columns)} Spalten")

    # Spalten-Mapping
    guess = _guess_columns(df)
    st.markdown("**Spalten zuordnen**")
    cols = [None] + list(df.columns)

    col1, col2, col3 = st.columns(3)
    name_col = col1.selectbox("Artikel (Pflicht)", cols, index=cols.index(guess["name"]) if guess["name"] in cols else 0, key="map_name")
    unit_col = col2.selectbox("Einheit (optional)", cols, index=cols.index(guess["unit"]) if guess["unit"] in cols else 0, key="map_unit")
    qty_col  = col3.selectbox("Menge/Bestand (optional)", cols, index=cols.index(guess["stock_qty"]) if guess["stock_qty"] in cols else 0, key="map_qty")

    col4, col5 = st.columns(2)
    price_col = col4.selectbox("Einkaufspreis (optional)", cols, index=cols.index(guess["purchase_price"]) if guess["purchase_price"] in cols else 0, key="map_price")
    cat_col   = col5.selectbox("Kategorie (optional)", cols, index=cols.index(guess["category"]) if guess["category"] in cols else 0, key="map_cat")

    if not name_col:
        st.error("Bitte mindestens die Spalte **Artikel** zuordnen.")
        return None, None

    mapping = {
        "name": name_col,
        "unit": unit_col,
        "stock_qty": qty_col,
        "purchase_price": price_col,
        "category": cat_col
    }

    return df, mapping

# ---------------------- Schritt 2: Bereinigen & Bearbeiten ----------------------

def _clean_dataframe(df: pd.DataFrame, mapping: Dict[str, Optional[str]]) -> pd.DataFrame:
    cats = _get_categories()

    out_rows = []
    for _, row in df.iterrows():
        raw_name = str(row[mapping["name"]]) if mapping["name"] else ""
        if not raw_name or str(raw_name).strip() == "":
            continue

        # Einheit aus eigener Spalte?
        unit_from_col = None
        if mapping["unit"]:
            unit_from_col = str(row[mapping["unit"]]) if not pd.isna(row[mapping["unit"]]) else None

        # Menge/Bestand
        qty = 0.0
        if mapping["stock_qty"]:
            try:
                qty = float(str(row[mapping["stock_qty"]]).replace(",", "."))
            except Exception:
                qty = 0.0

        # Preis
        price = 0.0
        if mapping["purchase_price"]:
            try:
                price = float(str(row[mapping["purchase_price"]]).replace(",", "."))
            except Exception:
                price = 0.0

        # Kategorie
        cat = None
        if mapping["category"]:
            val = row[mapping["category"]]
            cat = None if pd.isna(val) else str(val).strip() or None

        # Einheit parsen
        clean_name, amt, unit = _parse_unit_from_name(raw_name)

        # Falls eigene Einheitsspalte gesetzt ist & sinnvoll wirkt, nutze diese priorisiert
        if unit_from_col and str(unit_from_col).strip():
            # Versuche Werte wie "0,2l", "4 cl", "500 ml" etc.
            c2, amt2, unit2 = _parse_unit_from_name(str(unit_from_col))
            # Falls _parse_unit_from_name die Zeichenkette praktisch "nicht" parsen konnte
            # (z. B. "Stk"), versuchen wir einfache Zuordnung:
            if unit2 == "" and c2 == unit_from_col:
                txt = str(unit_from_col).strip().lower()
                # beliebte Kurzformen:
                if re.search(r'\d', txt):
                    # enthält Zahlen, trotzdem nochmal Regex:
                    c3, amt3, unit3 = _parse_unit_from_name(txt)
                    if unit3 != "":
                        amt, unit = amt3, unit3
                else:
                    # keine Zahl -> Einheit ohne Menge (e.g. "Stk")
                    amt, unit = (1.0, txt)
            else:
                amt, unit = amt2, unit2

        # Auto-Kategorie bei Bedarf
        if not cat:
            cat = _auto_category(clean_name, cats)

        out_rows.append({
            "name": clean_name,
            "unit_amount": float(amt or 0.0),
            "unit": unit or "",
            "stock_qty": float(qty or 0.0),
            "purchase_price": float(price or 0.0),
            "category": cat or ""
        })

    return pd.DataFrame(out_rows, columns=["name","unit_amount","unit","stock_qty","purchase_price","category"])

def _step_review_and_edit(clean_df: pd.DataFrame) -> pd.DataFrame:
    section_title("🧹 Prüfen & Bearbeiten")
    st.caption("Du kannst die Daten hier direkt anpassen (Name, Einheit, Menge, Einkaufspreis, Kategorie).")

    # Data Editor – mit etwas angenehmer Höhe
    edited = st.data_editor(
        clean_df,
        use_container_width=True,
        key="imp_editor",
        height=min(600, 120 + 28 * max(3, len(clean_df))),
        num_rows="dynamic",
        column_config={
            "name": {"header": "Artikel"},
            "unit_amount": {"header": "Menge (Einheit)"},
            "unit": {"header": "Einheit"},
            "stock_qty": {"header": "Bestand"},
            "purchase_price": {"header": "EK netto (€)"},
            "category": {"header": "Kategorie"},
        }
    )
    return edited

# ---------------------- Schritt 3: Speichern ----------------------

def _upsert_items(rows: List[Dict]):
    """Upsert (name, unit_amount, unit) → update stock_qty, purchase_price, category, created_at."""
    _ensure_items_table()
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        for r in rows:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            ua = float(r.get("unit_amount") or 0.0)
            un = (r.get("unit") or "").strip()
            sq = float(r.get("stock_qty") or 0.0)
            pp = float(r.get("purchase_price") or 0.0)
            cat = (r.get("category") or "").strip() or None

            ex = c.execute(
                "SELECT id, created_at FROM items WHERE name=? AND unit_amount=? AND unit=?",
                (name, ua, un)
            ).fetchone()

            if ex:
                # Update Kernfelder
                c.execute(
                    "UPDATE items SET stock_qty=?, purchase_price=?, category=? WHERE id=?",
                    (sq, pp, cat, ex[0])
                )
                # created_at sicher auffüllen, falls leer
                c.execute(
                    "UPDATE items SET created_at=? WHERE id=? AND (created_at IS NULL OR created_at='')",
                    (now_iso, ex[0])
                )
            else:
                # Insert MIT created_at
                c.execute(
                    "INSERT INTO items(name, unit_amount, unit, stock_qty, purchase_price, category, created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (name, ua, un, sq, pp, cat, now_iso)
                )
        cn.commit()

def _step_save_to_db(clean_df: pd.DataFrame):
    section_title("✅ Übernehmen & Speichern")
    st.write(f"Es werden **{len(clean_df)}** Artikel in die Datenbank geschrieben (Upsert).")
    if st.button("In Datenbank übernehmen", type="primary", use_container_width=True):
        try:
            _upsert_items(clean_df.to_dict(orient="records"))
            st.success("Import erfolgreich gespeichert.")
        except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")

# ---------------------- Kategorien verwalten ----------------------

def _render_categories_admin():
    section_title("🏷️ Kategorien verwalten")
    cats = _get_categories()

    st.caption("Definiere Kategorien und optionale Schlüsselwörter für die automatische Zuordnung beim Import.")

    # Editorfreundliche Darstellung
    df = pd.DataFrame([
        {"Kategorie": c.get("name",""), "Keywords (kommagetrennt)": ", ".join(c.get("keywords", []))}
        for c in cats
    ])

    edited = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",
        height=min(500, 120 + 28 * max(3, len(df)))
    )

    if st.button("💾 Kategorien speichern", use_container_width=True):
        new_cats: List[Dict] = []
        for _, row in edited.iterrows():
            name = (row.get("Kategorie") or "").strip()
            if not name:
                continue
            kw_raw = (row.get("Keywords (kommagetrennt)") or "").strip()
            kws = [k.strip() for k in kw_raw.split(",") if k.strip()]
            new_cats.append({"name": name, "keywords": kws})
        _save_categories(new_cats)
        st.success("Kategorien gespeichert.")

# ---------------------- Öffentliche Render-Funktion ----------------------

def render_data_tools():
    """
    Wird von admin.py (Tab „📦 Daten“) aufgerufen.
    Bietet zwei Unterbereiche: Import & Kategorien – ohne Sidebar.
    """
    _ensure_items_table()

    tabs = st.tabs(["⬆️ Import", "🏷️ Kategorien"])
    with tabs[0]:
        state = _get_state()

        if state.imp_step == 1:
            df, mapping = _step_upload_and_map()
            if df is not None and mapping is not None:
                # Sanity: name muss zugeordnet sein
                if mapping["name"] is None:
                    st.error("Bitte eine Spalte für **Artikel** wählen.")
                else:
                    st.session_state.imp_raw_df = df
                    st.session_state.imp_mapping = mapping
                    if st.button("Weiter ➜ Prüfen & Bearbeiten", use_container_width=True):
                        st.session_state.imp_step = 2
                        st.rerun()

        elif state.imp_step == 2:
            if state.imp_raw_df is None or state.imp_mapping is None:
                st.warning("Bitte zuerst eine Datei hochladen.")
                st.session_state.imp_step = 1
                st.rerun()

            clean_df = _clean_dataframe(state.imp_raw_df, state.imp_mapping)
            st.session_state.imp_clean_df = _step_review_and_edit(clean_df)

            btns = st.columns([1,1,6])
            if btns[0].button("← Zurück", use_container_width=True):
                st.session_state.imp_step = 1
                st.rerun()
            if btns[1].button("Weiter ➜ Speichern", type="primary", use_container_width=True):
                st.session_state.imp_step = 3
                st.rerun()

        elif state.imp_step == 3:
            if state.imp_clean_df is None or state.imp_clean_df.empty:
                st.warning("Keine Daten zum Speichern vorhanden.")
                state.imp_step = 2
                st.rerun()
            _step_save_to_db(state.imp_clean_df)

            if st.button("Neuen Import starten", use_container_width=True):
                st.session_state.imp_raw_df = None
                st.session_state.imp_mapping = None
                st.session_state.imp_clean_df = None
                st.session_state.imp_step = 1
                st.rerun()

    with tabs[1]:
        _render_categories_admin()
