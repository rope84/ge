import streamlit as st
import pandas as pd
from core.db import conn
from core.ui_theme import section_title


# ---------------------- DB Setup ----------------------

def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()

        # Benutzer
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT,
            first_name TEXT,
            last_name TEXT,
            role TEXT NOT NULL,
            functions TEXT DEFAULT '',
            passhash TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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

    tabs = st.tabs(["📊 Übersicht", "👥 Benutzer", "🔍 Suche", "⚙️ Funktionen"])

    # --- TAB 1: Statistik / Übersicht ---
    with tabs[0]:
        with conn() as cn:
            c = cn.cursor()
            roles = c.execute("SELECT role, COUNT(*) FROM users GROUP BY role").fetchall()
            total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        st.subheader("Benutzerübersicht")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Gesamt", total)
        for i, (role, count) in enumerate(roles):
            st.metric(role.capitalize(), count)

        st.divider()
        if roles:
            st.bar_chart(pd.DataFrame(roles, columns=["Rolle", "Anzahl"]).set_index("Rolle"))
        else:
            st.info("Noch keine Benutzer vorhanden.")

    # --- TAB 2: Benutzerliste & Bearbeiten ---
    with tabs[1]:
        st.subheader("Benutzerverwaltung")

        with conn() as cn:
            c = cn.cursor()
            users = c.execute(
                "SELECT id, username, email, first_name, last_name, role, functions FROM users ORDER BY id"
            ).fetchall()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

        if not users:
            st.info("Noch keine Benutzer angelegt.")
        else:
            df = pd.DataFrame(users, columns=["ID", "Benutzername", "E-Mail", "Vorname", "Nachname", "Rolle", "Funktionen"])
            st.dataframe(df.drop(columns=["ID"]), use_container_width=True, height=350)

            st.divider()
            st.subheader("Benutzer bearbeiten")

            selected = st.selectbox("Wähle Benutzer", df["Benutzername"])
            if selected:
                row = df[df["Benutzername"] == selected].iloc[0]
                e_email = st.text_input("E-Mail", row["E-Mail"])
                e_first = st.text_input("Vorname", row["Vorname"])
                e_last = st.text_input("Nachname", row["Nachname"])
                e_role = st.selectbox("Rolle", sorted(df["Rolle"].unique()), index=sorted(df["Rolle"].unique()).index(row["Rolle"]))
                e_funcs = st.multiselect("Funktionen", func_list, default=[f.strip() for f in (row["Funktionen"] or "").split(",") if f.strip()])

                if st.button("💾 Änderungen speichern"):
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("""
                            UPDATE users SET email=?, first_name=?, last_name=?, role=?, functions=? WHERE id=?
                        """, (e_email, e_first, e_last, e_role, ", ".join(e_funcs), int(row["ID"])))
                        cn.commit()
                    st.success("Benutzer aktualisiert.")
                    st.rerun()

        st.divider()
        st.subheader("Neuen Benutzer hinzufügen")
        with st.form("add_user_form"):
            c1, c2 = st.columns(2)
            username = c1.text_input("Benutzername")
            email = c2.text_input("E-Mail")
            c3, c4 = st.columns(2)
            first_name = c3.text_input("Vorname")
            last_name = c4.text_input("Nachname")
            role = st.selectbox("Rolle", ["admin", "user", "inventur"], index=1)
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

    # --- TAB 3: Suche ---
    with tabs[2]:
        st.subheader("🔍 Benutzer suchen & bearbeiten")
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
                df = pd.DataFrame(results, columns=["ID", "Benutzername", "E-Mail", "Vorname", "Nachname", "Rolle", "Funktionen"])
                st.dataframe(df.drop(columns=["ID"]), use_container_width=True, height=350)
                selected = st.selectbox("Benutzer auswählen", df["Benutzername"])
                if selected:
                    user_row = df[df["Benutzername"] == selected].iloc[0]
                    new_role = st.selectbox("Neue Rolle", sorted(df["Rolle"].unique()), index=sorted(df["Rolle"].unique()).index(user_row["Rolle"]))
                    new_funcs = st.multiselect("Funktionen", func_list, default=[f.strip() for f in (user_row["Funktionen"] or "").split(",") if f.strip()])
                    if st.button("💾 Änderungen speichern", key="search_edit"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("UPDATE users SET role=?, functions=? WHERE id=?", (new_role, ", ".join(new_funcs), int(user_row["ID"])))
                            cn.commit()
                        st.success("Benutzer aktualisiert.")
                        st.rerun()
            else:
                st.info("Keine Benutzer gefunden.")

    # --- TAB 4: Funktionen ---
    with tabs[3]:
        section_title("⚙️ Rollen & Funktionen")
        with conn() as cn:
            c = cn.cursor()
            funcs = c.execute("SELECT id, name, description FROM functions ORDER BY name").fetchall()

        df = pd.DataFrame(funcs, columns=["ID", "Funktion", "Beschreibung"])
        edited = st.data_editor(
            df.drop(columns=["ID"]),
            use_container_width=True,
            num_rows="dynamic",
            key="func_editor",
            height=400
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
