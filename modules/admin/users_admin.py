import streamlit as st
import pandas as pd
from core.db import conn
from core.ui_theme import section_title

def render_users_admin():
    section_title("👥 Benutzerverwaltung (modernisiert)")
    st.caption("users_admin.py geladen ✅")

    # Tabellen prüfen
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT,
            first_name TEXT,
            last_name TEXT,
            role TEXT NOT NULL,
            functions TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
        """)
        have = c.execute("SELECT COUNT(*) FROM functions").fetchone()[0]
        if have == 0:
            defaults = [
                ("Admin", "Vollzugriff auf alle Module"),
                ("Barleiter", "Zugriff auf Bar & Planung"),
                ("Lager", "Inventur & Artikelverwaltung"),
                ("Inventur", "Nur Bestandsansicht")
            ]
            c.executemany("INSERT INTO functions(name, description) VALUES(?,?)", defaults)
        cn.commit()

    tabs = st.tabs(["📊 Übersicht", "👥 Benutzer", "🔍 Suche", "⚙️ Funktionen"])

    # TAB 1 – Übersicht
    with tabs[0]:
        with conn() as cn:
            c = cn.cursor()
            roles = c.execute("SELECT role, COUNT(*) FROM users GROUP BY role").fetchall()
            total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        col1, col2 = st.columns(2)
        col1.metric("Gesamtanzahl", total)
        if roles:
            df_roles = pd.DataFrame(roles, columns=["Rolle", "Anzahl"]).set_index("Rolle")
            st.bar_chart(df_roles)
        else:
            st.info("Noch keine Benutzer vorhanden.")

    # TAB 2 – Benutzerverwaltung
    with tabs[1]:
        with conn() as cn:
            c = cn.cursor()
            users = c.execute(
                "SELECT id, username, email, first_name, last_name, role, functions FROM users ORDER BY id"
            ).fetchall()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

        if not users:
            st.info("Noch keine Benutzer angelegt.")
        else:
            df = pd.DataFrame(users, columns=["ID","Benutzername","E-Mail","Vorname","Nachname","Rolle","Funktionen"])
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
            role = st.selectbox("Rolle", ["admin","user","inventur"], index=1)
            selected_funcs = st.multiselect("Funktionen", func_list)
            if st.form_submit_button("➕ Benutzer erstellen"):
                if not username:
                    st.warning("Benutzername erforderlich.")
                else:
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("""
                            INSERT INTO users(username, email, first_name, last_name, role, functions)
                            VALUES(?,?,?,?,?,?)
                        """, (username, email, first_name, last_name, role, ", ".join(selected_funcs)))
                        cn.commit()
                    st.success(f"Benutzer '{username}' angelegt.")
                    st.rerun()

    # TAB 3 – Suche
    with tabs[2]:
        st.subheader("Benutzer suchen & bearbeiten")
        query = st.text_input("Suchbegriff (Name, E-Mail, Rolle ...)")
        if query:
            with conn() as cn:
                c = cn.cursor()
                results = c.execute("""
                    SELECT id, username, email, first_name, last_name, role, functions
                    FROM users
                    WHERE username LIKE ? OR email LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR role LIKE ? OR functions LIKE ?
                    ORDER BY username
                """, tuple([f"%{query}%"] * 6)).fetchall()

            if results:
                df = pd.DataFrame(results, columns=["ID","Benutzername","E-Mail","Vorname","Nachname","Rolle","Funktionen"])
                st.dataframe(df.drop(columns=["ID"]), use_container_width=True, height=300)
            else:
                st.info("Keine Treffer.")

    # TAB 4 – Funktionen
    with tabs[3]:
        st.subheader("Funktionen verwalten")
        with conn() as cn:
            c = cn.cursor()
            funcs = c.execute("SELECT id,name,description FROM functions ORDER BY name").fetchall()
        df = pd.DataFrame(funcs, columns=["ID","Funktion","Beschreibung"])
        edited = st.data_editor(df.drop(columns=["ID"]), use_container_width=True, num_rows="dynamic")
        if st.button("💾 Änderungen speichern"):
            with conn() as cn:
                c = cn.cursor()
                c.execute("DELETE FROM functions")
                for _, row in edited.iterrows():
                    n = row["Funktion"].strip()
                    d = (row["Beschreibung"] or "").strip()
                    if n:
                        c.execute("INSERT INTO functions(name, description) VALUES(?,?)", (n, d))
                cn.commit()
            st.success("Funktionen gespeichert.")
            st.rerun()
