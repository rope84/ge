import streamlit as st
import pandas as pd
from core.db import conn
from core.ui_theme import section_title


# ---------- kleines CSS für Soft-Cards & saubere Abstände ----------
_CARD_CSS = """
<style>
.ge-card {
  border-radius: 14px;
  padding: 14px 16px;
  background: rgba(255,255,255,0.03);
  box-shadow: 0 6px 16px rgba(0,0,0,0.15);
  border: 1px solid rgba(255,255,255,0.06);
}
.ge-pill {
  display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px;
  border:1px solid rgba(255,255,255,0.18); opacity:0.9;
}
.ge-muted { opacity:0.8; font-size:12px; }
</style>
"""


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
            defaults = [
                ("Admin", "Vollzugriff auf alle Module"),
                ("Barleiter", "Zugriff auf Barumsätze & Personalplanung"),
                ("Lager", "Zugriff auf Inventur und Artikelverwaltung"),
                ("Inventur", "Nur Inventur- und Bestandseinsicht"),
            ]
            c.executemany("INSERT INTO functions(name, description) VALUES(?,?)", defaults)
        cn.commit()


def render_users_admin():
    st.markdown(_CARD_CSS, unsafe_allow_html=True)  # Design aktivieren
    section_title("👤 Benutzer & Mitarbeiter")
    _ensure_tables()

    tabs = st.tabs(["📊 Übersicht", "👥 Benutzer", "🔍 Suche", "⚙️ Funktionen"])

    # --- TAB 1: Übersicht ---
    with tabs[0]:
        with conn() as cn:
            c = cn.cursor()
            total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            roles = c.execute("SELECT role, COUNT(*) FROM users GROUP BY role").fetchall()
            last_user = c.execute("""
                SELECT username, COALESCE(created_at, '') FROM users
                ORDER BY datetime(created_at) DESC LIMIT 1
            """).fetchone()

        col1, col2, col3 = st.columns(3)
        with col1: st.metric("👥 Gesamt", total)
        with col2: st.metric("🧩 Rollen (distinct)", len(roles))
        with col3: st.metric("🕒 Letzter Eintrag", last_user[1][:16] if last_user else "—")

        st.write("")
        with st.container():
            st.markdown("<div class='ge-card'>", unsafe_allow_html=True)
            st.subheader("Verteilung nach Rollen", divider="gray")
            if roles:
                chart_df = pd.DataFrame(roles, columns=["Rolle", "Anzahl"]).set_index("Rolle")
                st.bar_chart(chart_df, height=280)
            else:
                st.info("Noch keine Benutzer vorhanden.")
            st.markdown("</div>", unsafe_allow_html=True)

    # --- TAB 2: Benutzer ---
    with tabs[1]:
        with conn() as cn:
            c = cn.cursor()
            users = c.execute("""
                SELECT id, username, email, first_name, last_name, role, functions
                FROM users ORDER BY username
            """).fetchall()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

        st.markdown("<div class='ge-card'>", unsafe_allow_html=True)
        st.subheader("Benutzerliste", divider="gray")
        if not users:
            st.info("Noch keine Benutzer angelegt.")
        else:
            df = pd.DataFrame(users, columns=["ID","Benutzername","E-Mail","Vorname","Nachname","Rolle","Funktionen"])
            st.dataframe(df.drop(columns=["ID"]), use_container_width=True, height=280)
        st.markdown("</div>", unsafe_allow_html=True)

        st.write("")
        st.markdown("<div class='ge-card'>", unsafe_allow_html=True)
        st.subheader("Benutzer bearbeiten", divider="gray")
        if users:
            df = pd.DataFrame(users, columns=["ID","Benutzername","E-Mail","Vorname","Nachname","Rolle","Funktionen"])
            selected_user = st.selectbox("Wähle Benutzer", df["Benutzername"])
            if selected_user:
                row = df[df["Benutzername"] == selected_user].iloc[0]
                e_email = st.text_input("📧 E-Mail", row["E-Mail"])
                e_first = st.text_input("🧍 Vorname", row["Vorname"])
                e_last = st.text_input("🧍 Nachname", row["Nachname"])
                # Rolle-Dropdown dynamisch aus vorhandenen Rollen + Standardvorschlag
                available_roles = sorted(set(df["Rolle"].tolist() + ["admin","user","inventur"]))
                e_role = st.selectbox("🛠 Rolle", available_roles, index=available_roles.index(row["Rolle"]) if row["Rolle"] in available_roles else 0)
                # Funktionen hübsch via Multiselect
                defaults = [f.strip() for f in (row["Funktionen"] or "").split(",") if f.strip()]
                e_funcs = st.multiselect("🎛 Zusatzfunktionen", func_list, default=defaults)

                c1, c2 = st.columns(2)
                if c1.button("💾 Änderungen speichern", use_container_width=True):
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("""
                            UPDATE users SET email=?, first_name=?, last_name=?, role=?, functions=? WHERE id=?
                        """, (e_email, e_first, e_last, e_role, ", ".join(e_funcs), int(row["ID"])))
                        cn.commit()
                    st.success("✅ Benutzer aktualisiert.")
                    st.rerun()
                if c2.button("🗑 Benutzer löschen", use_container_width=True):
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("DELETE FROM users WHERE id=?", (int(row["ID"]),))
                        cn.commit()
                    st.warning(f"Benutzer '{selected_user}' gelöscht.")
                    st.rerun()
        else:
            st.caption("—")
        st.markdown("</div>", unsafe_allow_html=True)

        st.write("")
        st.markdown("<div class='ge-card'>", unsafe_allow_html=True)
        st.subheader("➕ Neuer Benutzer", divider="gray")
        with conn() as cn:
            c = cn.cursor()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]
        with st.form("add_user_form"):
            c1, c2 = st.columns(2)
            username = c1.text_input("Benutzername")
            email = c2.text_input("E-Mail")
            c3, c4 = st.columns(2)
            first_name = c3.text_input("Vorname")
            last_name  = c4.text_input("Nachname")
            role = st.selectbox("Rolle", ["admin","user","inventur"], index=1)
            selected_funcs = st.multiselect("Funktionen", func_list)
            password = st.text_input("Passwort", type="password")
            submit_new = st.form_submit_button("✅ Benutzer anlegen", use_container_width=True)
        if submit_new:
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
                    st.success(f"Benutzer '{username}' erfolgreich angelegt.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fehler beim Anlegen: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- TAB 3: Suche ---
    with tabs[2]:
        st.markdown("<div class='ge-card'>", unsafe_allow_html=True)
        st.subheader("🔍 Benutzer suchen & bearbeiten", divider="gray")

        query = st.text_input("Suchbegriff (Name, E-Mail, Rolle, Funktion …)")
        func_list = []
        with conn() as cn:
            c = cn.cursor()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]
        if query.strip():
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
                st.dataframe(df.drop(columns=["ID"]), use_container_width=True, height=260)

                selected = st.selectbox("Treffer auswählen", df["Benutzername"])
                if selected:
                    u = df[df["Benutzername"] == selected].iloc[0]
                    roles_av = sorted(set(df["Rolle"].tolist() + ["admin","user","inventur"]))
                    new_role = st.selectbox("Neue Rolle", roles_av, index=roles_av.index(u["Rolle"]) if u["Rolle"] in roles_av else 0)
                    new_funcs = st.multiselect("Funktionen", func_list, default=[f.strip() for f in (u["Funktionen"] or "").split(",") if f.strip()])
                    if st.button("💾 Änderungen speichern", key=f"search_edit_{u['ID']}", use_container_width=True):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("UPDATE users SET role=?, functions=? WHERE id=?", (new_role, ", ".join(new_funcs), int(u["ID"])))
                            cn.commit()
                        st.success("Benutzer geändert.")
                        st.rerun()
            else:
                st.info("Keine Benutzer gefunden.")
        else:
            st.caption("Gib oben einen Suchbegriff ein.")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- TAB 4: Funktionen ---
    with tabs[3]:
        section_title("⚙️ Rollen & Funktionen")
        with conn() as cn:
            c = cn.cursor()
            funcs = c.execute("SELECT id, name, description FROM functions ORDER BY name").fetchall()

        df = pd.DataFrame(funcs, columns=["ID","Funktion","Beschreibung"])
        edited = st.data_editor(
            df.drop(columns=["ID"]),
            use_container_width=True,
            num_rows="dynamic",
            key="func_editor",
            height=380
        )

        if st.button("💾 Änderungen speichern", use_container_width=True):
            with conn() as cn:
                c = cn.cursor()
                c.execute("DELETE FROM functions")
                for _, row in edited.iterrows():
                    name = (row.get("Funktion") or "").strip()
                    desc = (row.get("Beschreibung") or "").strip()
                    if name:
                        c.execute("INSERT INTO functions(name, description) VALUES(?,?)", (name, desc))
                cn.commit()
            st.success("Funktionen gespeichert.")
            st.rerun()
