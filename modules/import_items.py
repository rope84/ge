import streamlit as st
import pandas as pd
from core.db import conn
from core.ui_theme import section_title

# -------------------------------
# Hilfsfunktionen
# -------------------------------
def _ensure_items_table():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                unit TEXT,
                stock_qty REAL NOT NULL DEFAULT 0,
                purchase_price REAL NOT NULL DEFAULT 0,
                category TEXT,
                total_value REAL NOT NULL DEFAULT 0
            )
        """)
        cn.commit()


def _save_items(df: pd.DataFrame):
    _ensure_items_table()
    with conn() as cn:
        c = cn.cursor()
        for _, row in df.iterrows():
            name = str(row["Artikel"]).strip()
            unit = str(row.get("Einheit", "")).strip()
            qty = float(row.get("Menge", 0))
            price = float(row.get("Einkaufspreis", 0))
            total = qty * price
            cat = str(row.get("Kategorie", "")).strip()
            c.execute("""
                INSERT OR REPLACE INTO items(name, unit, stock_qty, purchase_price, category, total_value)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, unit, qty, price, cat, total))
        cn.commit()

# -------------------------------
# Haupt-UI
# -------------------------------
def render_import_items():
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("📦 Artikelimport & Verwaltung")
    st.caption("Lade deine Getränkedaten hoch, ordne die Spalten zu und speichere sie in die Datenbank.")

    if "import_stage" not in st.session_state:
        st.session_state.import_stage = "upload"
        st.session_state.df_preview = None
        st.session_state.mapping = {}

    # ---------------- SCHRITT 1: UPLOAD ----------------
    if st.session_state.import_stage == "upload":
        uploaded = st.file_uploader("Excel-Datei auswählen", type=["xlsx", "xls"])
        if uploaded:
            try:
                df = pd.read_excel(uploaded)
                df.columns = [str(c).strip() for c in df.columns]
                st.success(f"✅ Datei geladen – {len(df)} Zeilen, {len(df.columns)} Spalten.")
                st.dataframe(df.head(), use_container_width=True)

                # Vorschlag für Spaltenzuordnung
                possible_mappings = {
                    "Artikel": next((c for c in df.columns if "art" in c.lower() or "produkt" in c.lower()), None),
                    "Einheit": next((c for c in df.columns if "einheit" in c.lower() or "menge" in c.lower()), None),
                    "Menge": next((c for c in df.columns if "bestand" in c.lower() or "stand" in c.lower()), None),
                    "Einkaufspreis": next((c for c in df.columns if "preis" in c.lower() or "netto" in c.lower()), None),
                    "Kategorie": next((c for c in df.columns if "kategorie" in c.lower() or "gruppe" in c.lower()), None),
                }

                st.markdown("### 🔠 Spaltenzuordnung")
                st.caption("Ordne hier deine Excel-Spalten den richtigen Feldern zu:")

                mapping = {}
                cols = list(df.columns)
                for field, suggestion in possible_mappings.items():
                    mapping[field] = st.selectbox(
                        f"{field}-Spalte auswählen",
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

        # Neue DataFrame-Struktur aufbauen
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

        st.markdown("### ✏️ Artikeldaten überprüfen & anpassen")
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
