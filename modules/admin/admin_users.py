import streamlit as st
import pandas as pd
from core.db import conn
from core.ui_theme import section_title
import datetime

# ---------------------- DB Setup ----------------------

def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()

        # Benutzer-Tabelle (User = Mitarbeiter)
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT,
            first_name TEXT,
            last_name TEXT,
            role TEXT NOT NULL,          -- Hauptrolle (admin, user, etc.)
            functions TEXT DEFAULT '',   -- Kommagetrennte Zusatzfunktionen (Barleiter, Lager ...)
            passhash TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        # Funktionskatalog
        c.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
        """)

        # Beispielwerte
        have = c.execute("SELECT COUNT(*) FROM functions").fetchone()[0]
        if have == 0:
            default = [
                ("Admin", "Vollzugriff auf alle Module"),
                ("Barleiter", "Zugriff auf Barumsätze & Personalplanung"),
                ("Lager", "Zugriff auf Inventur und Artikelverwaltung"),
                ("Inventur", "Nur Inventur- und Bestandseinsicht")
            ]
            c.executemany("INSERT INTO functions(name, description) VALUES(?,?)", default)
        cn.commit()


# ---------------------- Benutzerverwaltung ----------------------

def _render_user_admin():
    section_title("👤 Benutzer & Mitarbeiter")
    _ensure_tables()

    tabs = st.tabs(["👥 Benutzerliste", "⚙️ Funktionen verwalten"])

    # TAB 1 – Benutzerliste
    with tabs[0]:
        with conn() as cn:
            c = cn.cursor()
            users = c.execute(
                "SELECT id, username, email, first_name, last_name, role, functions FROM users ORDER BY id"
            ).fetchall()

        st.subheader("Benutzerübersicht")

        if not users:
            st.info("Noch keine Benutzer angelegt.")
        else:
            df = pd.DataFrame(users, columns=["ID", "Benutzername", "E-Mail", "Vorname", "Nachname", "Rolle", "Funktionen"])
            st.dataframe(df.drop(columns=["ID"]), use_container_width=True, height=350)

        st.divider()
        st.subheader("Neuen Benutzer anlegen")

        with st.form("add_user_form"):
            c1, c2 = st.columns(2)
            username = c1.text_input("Benutzername")
            email = c2.text_input("E-Mail")

            c3, c4 = st.columns(2)
            first_name = c3.text_input("Vorname")
            last_name = c4.text_input("Nachname")

            role = st.selectbox("Rolle", ["admin", "user", "inventur"], index=1)
            with conn() as cn:
                c = cn.cursor()
                func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

            selected_funcs = st.multiselect("Funktionen", func_list)
            password = st.text_input("Passwort", type="password")

            if st.form_submit_button("➕ Benutzer erstellen"):
                if not username or not password:
                    st.warning("Benutzername und Passwort erforderlich.")
                else:
                    try:
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("""
                            INSERT INTO users(username, email, first_name, last_name, role, functions, passhash)
                            VALUES(?,?,?,?,?,?, '')
                            """, (username, email, first_name, last_name, role, ", ".join(selected_funcs)))
                            cn.commit()
                        st.success(f"Benutzer '{username}' angelegt.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fehler beim Anlegen: {e}")

    # TAB 2 – Funktionen verwalten
    with tabs[1]:
        section_title("⚙️ Rollen & Funktionen")
        with conn() as cn:
            c = cn.cursor()
            funcs = c.execute("SELECT id, name, description FROM functions ORDER BY name").fetchall()

        df = pd.DataFrame(funcs, columns=["ID", "Funktion", "Beschreibung"])
        edited = st.data_editor(
            df.drop(columns=["ID"]),
            use_container_width=True,
            num_rows="dynamic",
            key="func_editor"
        )

        if st.button("💾 Änderungen speichern", use_container_width=True):
            with conn() as cn:
                c = cn.cursor()
                c.execute("DELETE FROM functions")
                for _, row in edited.iterrows():
                    name = row["Funktion"].strip()
                    desc = row["Beschreibung"].strip() if row["Beschreibung"] else ""
                    if name:
                        c.execute("INSERT INTO functions(name, description) VALUES(?,?)", (name, desc))
                cn.commit()
            st.success("Funktionen gespeichert.")
            st.rerun()
