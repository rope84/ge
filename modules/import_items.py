import streamlit as st
import pandas as pd
from core.db import conn
from core.ui_theme import section_title

# -------------------------------
# Hilfsfunktionen
# -------------------------------

def _ensure_items_table():
    """Stellt sicher, dass Tabelle 'items' existiert und alle benötigten Spalten enthält."""
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                unit TEXT,
                stock_qty REAL NOT NULL DEFAULT 0
            )
        """)
        cn.commit()

        # Prüfen, ob Spalten fehlen und ergänzen
        cols = [r[1] for r in c.execute("PRAGMA table_info(items)").fetchall()]
        add_cols = []
        if "purchase_price" not in cols:
            add_cols.append(("purchase_price", "REAL NOT NULL DEFAULT 0"))
        if "category" not in cols:
            add_cols.append(("category", "TEXT"))
        if "total_value" not in cols:
            add_cols.append(("total_value", "REAL NOT NULL DEFAULT 0"))

        for col, typ in add_cols:
            c.execute(f"ALTER TABLE items ADD COLUMN {col} {typ}")
        cn.commit()


def _save_items(df: pd.DataFrame):
    """Schreibt DataFrame in Tabelle 'items'."""
    _ensure_items_table()
    with conn() as cn:
        c = cn.cursor()
        for _, row in df.iterrows():
            name = str(row.get("Artikel", "")).strip()
            if not name:
                continue
            unit = str(row.get("Einheit", "")).strip()
            qty = float(row.get("Menge", 0) or 0)
            price = float(row.get("Einkaufspreis", 0) or 0)
            cat = str(row.get("Kategorie", "")).strip()
            total = qty * price
            c.execute("""
                INSERT OR REPLACE INTO items(name, unit, stock_qty, purchase_price, category, total_value)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, unit, qty, price, cat, total))
        cn.commit()


def _styled_box(title, content, color="#1E1E1E"):
    """Schöne Box mit Schatten und Titel."""
    st.markdown(
        f"""
        <div style="
            background:{color};
            padding:18px 22px;
            border-radius:16px;
            box-shadow: 0 6px 16px rgba(0,0,0,0.3);
            margin-top:16px;
            ">
            <h4 style="margin-bottom:8px; color:#fff;">{title}</h4>
            <div style="font-size:13px; color:#ddd;">{content}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


# -------------------------------
# Haupt-UI
# -------------------------------
def render_import_items():
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("📦 Artikelimport & Verwaltung")
    st.caption("Importiere Getränkedaten per Excel, überprüfe und speichere sie in deine Datenbank.")

    if "import_stage" not in st.session_state:
        st.session_state.import_stage = "upload"
        st.session_state.df_preview = None
        st.session_state.mapping = {}

    # ---------------- SCHRITT 1: UPLOAD ----------------
    if st.session_state.import_stage == "upload":
        _styled_box(
            "1️⃣ Excel-Datei hochladen",
            "Erlaubt sind Formate **.xlsx** oder **.xls**. Enthaltene Spalten wie *Artikel, Einheit, Menge, Einkaufspreis, Kategorie* werden automatisch erkannt."
        )

        uploaded = st.file_uploader("Datei auswählen", type=["xlsx", "xls"], label_visibility="collapsed")
        if uploaded:
            try:
                df = pd.read_excel(uploaded)
                df.columns = [str(c).strip() for c in df.columns]
                st.success(f"✅ Datei geladen – {len(df)} Zeilen, {len(df.columns)} Spalten.")
                st.dataframe(df.head(), use_container_width=True)

                # Spaltenvorschläge automatisch erkennen
                possible_mappings = {
                    "Artikel": next((c for c in df.columns if "art" in c.lower() or "produkt" in c.lower()), None),
                    "Einheit": next((c for c in df.columns if "einheit" in c.lower() or "inhalt" in c.lower()), None),
                    "Menge": next((c for c in df.columns if "menge" in c.lower() or "bestand" in c.lower() or "stand" in c.lower()), None),
                    "Einkaufspreis": next((c for c in df.columns if "preis" in c.lower() or "netto" in c.lower()), None),
                    "Kategorie": next((c for c in df.columns if "kategorie" in c.lower() or "gruppe" in c.lower()), None),
                }

                _styled_box("2️⃣ Spaltenzuordnung", "Ordne hier die Excel-Spalten den richtigen Feldern zu:")

                mapping = {}
                cols = list(df.columns)
                for field, suggestion in possible_mappings.items():
                    mapping[field] = st.selectbox(
                        f"{field}-Spalte",
                        options=["<keine>"] + cols,
                        index=cols.index(suggestion) + 1 if suggestion in cols else 0
                    )

                if st.button("➡️ Weiter zur Bearbeitung", use_container_width=True):
                    st.session_state.mapping = mapping
                    st.session_state.df_preview = df
                    st.session_state.import_stage = "edit"
                    st.rerun()

            except Exception as e:
                st.error(f"Fehler beim Lesen der Datei: {e}")

    # ---------------- SCHRITT 2: BEARBEITUNG ----------------
    elif st.session_state.import_stage == "edit":
        df = st.session_state.df_preview
        mapping = st.session_state.mapping

        data = {
            "Artikel": df[mapping["Artikel"]] if mapping["Artikel"] != "<keine>" else "",
            "Einheit": df[mapping["Einheit"]] if mapping["Einheit"] != "<keine>" else "",
            "Menge": df[mapping["Menge"]] if mapping["Menge"] != "<keine>" else 0,
            "Einkaufspreis": df[mapping["Einkaufspreis"]] if mapping["Einkaufspreis"] != "<keine>" else 0,
            "Kategorie": df[mapping["Kategorie"]] if mapping["Kategorie"] != "<keine>" else "",
        }
        new_df = pd.DataFrame(data)
        new_df["Menge"] = pd.to_numeric(new_df["Menge"], errors="coerce").fillna(0)
        new_df["Einkaufspreis"] = pd.to_numeric(new_df["Einkaufspreis"], errors="coerce").fillna(0)
        new_df["Gesamtwert"] = new_df["Menge"] * new_df["Einkaufspreis"]

        _styled_box("3️⃣ Artikeldaten prüfen", "Bearbeite hier alle Felder direkt in der Tabelle.")
        edited = st.data_editor(new_df, use_container_width=True, hide_index=True, num_rows="dynamic", key="edited_items")

        col1, col2 = st.columns(2)
        if col1.button("⬅️ Zurück", use_container_width=True):
            st.session_state.import_stage = "upload"
            st.rerun()

        if col2.button("💾 In Datenbank speichern", use_container_width=True):
            try:
                _save_items(edited)
                st.success("🎉 Artikel erfolgreich gespeichert!")
                st.session_state.import_stage = "upload"
                st.session_state.df_preview = None
            except Exception as e:
                st.error(f"Fehler beim Speichern: {e}")
