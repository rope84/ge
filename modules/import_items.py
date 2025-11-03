import streamlit as st
import pandas as pd
from core.db import conn
from core.ui_theme import section_title

# -------------------------------
# Hilfsfunktionen
# -------------------------------
def _ensure_items_table():
    """Erstellt Tabelle 'items' falls nicht vorhanden."""
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
    """Schreibt DataFrame in Tabelle 'items'."""
    _ensure_items_table()
    with conn() as cn:
        c = cn.cursor()
        for _, row in df.iterrows():
            name = str(row["Artikel"]).strip()
            unit = str(row["Einheit"]).strip() if "Einheit" in row and pd.notna(row["Einheit"]) else ""
            qty = float(row["Menge"]) if "Menge" in row and pd.notna(row["Menge"]) else 0.0
            price = float(row["Einkaufspreis"]) if "Einkaufspreis" in row and pd.notna(row["Einkaufspreis"]) else 0.0
            total = qty * price
            cat = str(row["Kategorie"]) if "Kategorie" in row and pd.notna(row["Kategorie"]) else ""
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

    st.caption("Hier kannst du Getränkedaten per Excel hochladen, bearbeiten und in die Datenbank übernehmen.")

    # Zustand im Session State speichern (mehrstufiger Ablauf)
    if "import_stage" not in st.session_state:
        st.session_state.import_stage = "upload"
        st.session_state.df_preview = None

    # --- SCHRITT 1: Upload ---
    if st.session_state.import_stage == "upload":
        uploaded = st.file_uploader("Excel-Datei auswählen", type=["xlsx", "xls"])
        st.info("Die Datei sollte folgende Spalten enthalten: **Artikel, Einheit, Menge, Einkaufspreis** (optional Kategorie).")

        if uploaded:
            try:
                df = pd.read_excel(uploaded)

                # Spalten anpassen / Standardnamen
                expected = ["Artikel", "Einheit", "Menge", "Einkaufspreis"]
                df.columns = [col.strip() for col in df.columns]
                missing = [c for c in expected if c not in df.columns]
                if missing:
                    st.warning(f"⚠️ Folgende Spalten fehlen: {', '.join(missing)}")
                else:
                    st.success(f"✅ Datei erfolgreich geladen ({len(df)} Zeilen).")
                    st.dataframe(df, use_container_width=True, height=400)
                    st.session_state.df_preview = df
                    if st.button("➡️ Weiter zur Bearbeitung", use_container_width=True):
                        st.session_state.import_stage = "edit"
                        st.rerun()
            except Exception as e:
                st.error(f"Fehler beim Lesen der Datei: {e}")

    # --- SCHRITT 2: Bearbeitung ---
    elif st.session_state.import_stage == "edit":
        df = st.session_state.df_preview.copy()
        st.markdown("### ✏️ Artikel bearbeiten")

        edited = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key="edited_import_df"
        )

        col1, col2 = st.columns([1, 1])
        if col1.button("⬅️ Zurück", use_container_width=True):
            st.session_state.import_stage = "upload"
            st.rerun()

        if col2.button("💾 In Datenbank speichern", use_container_width=True):
            try:
                _save_items(edited)
                st.success("🎉 Artikel erfolgreich in die Datenbank übertragen!")
                st.session_state.import_stage = "upload"
                st.session_state.df_preview = None
            except Exception as e:
                st.error(f"Fehler beim Speichern: {e}")
