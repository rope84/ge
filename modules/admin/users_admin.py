import streamlit as st
import pandas as pd
from core.db import conn

# --- kleine Card-Helper (ähnlicher Look wie im Admin-Cockpit) ---
def _role_color(role: str) -> str:
    colors = {
        "admin": "#e11d48",     # rot
        "barlead": "#0ea5e9",   # blau
        "user": "#10b981",      # grün
        "inventur": "#f59e0b",  # orange
    }
    return colors.get(role, "#6b7280")  # grau

def _card(title: str, value: str, color: str) -> str:
    return f"""
    <div style="
        padding:12px 14px; border-radius:14px;
        background:rgba(255,255,255,0.03);
        box-shadow:0 6px 16px rgba(0,0,0,0.15);
        position:relative; overflow:hidden; min-height:74px;">
      <div style="
        position:absolute; left:0; top:0; bottom:0; width:6px;
        background: linear-gradient(180deg, {color}, {color}55);"></div>
      <div style="margin-left:12px;">
        <div style="font-size:12px;opacity:0.75;">{title}</div>
        <div style="font-size:22px;font-weight:800;margin-top:4px;">{value}</div>
      </div>
    </div>
    """

def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()
        # users
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT NOT NULL UNIQUE,
            email      TEXT,
            first_name TEXT,
            last_name  TEXT,
            role       TEXT NOT NULL,
            functions  TEXT DEFAULT '',
            passhash   TEXT NOT NULL DEFAULT '',
            created_at TEXT
        )
        """)
        # functions
        c.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
        """)
        if c.execute("SELECT COUNT(*) FROM functions").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO functions(name, description) VALUES(?,?)",
                [
                    ("Admin","Vollzugriff auf alle Module"),
                    ("Barleiter","Zugriff auf Bar & Planung"),
                    ("Lager","Inventur & Artikelverwaltung"),
                    ("Inventur","Nur Bestandsansicht")
                ]
            )
        cn.commit()

def render_users_admin():
    _ensure_tables()

    # Tabs: Übersicht (nur Zahlen), Benutzer, Suche, Funktionen
    tabs = st.tabs(["📊 Übersicht", "👤 Benutzer", "🔍 Suche", "⚙️ Funktionen"])

    # ------------------- TAB 1: Übersicht (nur Zahlen) -------------------
    with tabs[0]:
        with conn() as cn:
            c = cn.cursor()
            total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            rows  = c.execute("SELECT role, COUNT(*) FROM users GROUP BY role ORDER BY role").fetchall()

        # Erste Karte: Gesamt
        col_total = st.columns(1)[0]
        col_total.markdown(_card("Gesamtanzahl Benutzer", str(total), "#3b82f6"), unsafe_allow_html=True)
        st.write("")

        # Karten für Rollen, dynamisch
        if rows:
            # 4 Spalten-Grid
            def chunk(lst, n):
                for i in range(0, len(lst), n):
                    yield lst[i:i+n]

            for group in chunk(rows, 4):
                cols = st.columns(len(group))
                for (role, count), col in zip(group, cols):
                    col.markdown(_card(f"Rolle: {role}", str(count), _role_color(role)), unsafe_allow_html=True)
        else:
            st.info("Noch keine Benutzer vorhanden.")

    # ------------------- TAB 2: Benutzerliste & Bearbeiten -------------------
    with tabs[1]:
        with conn() as cn:
            c = cn.cursor()
            users = c.execute(
                "SELECT id, username, email, first_name, last_name, role, functions FROM users ORDER BY id"
            ).fetchall()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

        st.subheader("Benutzer")
        if not users:
            st.info("Noch keine Benutzer angelegt.")
        else:
            df = pd.DataFrame(users, columns=["ID","Benutzername","E-Mail","Vorname","Nachname","Rolle","Funktionen"])
            st.dataframe(df.drop(columns=["ID"]), use_container_width=True, height=320)

            st.divider()
            st.subheader("Benutzer bearbeiten")
            selected = st.selectbox("Wähle Benutzer", df["Benutzername"])
            if selected:
                row = df[df["Benutzername"] == selected].iloc[0]
                e_email = st.text_input("E-Mail", row["E-Mail"])
                e_first = st.text_input("Vorname", row["Vorname"])
                e_last  = st.text_input("Nachname", row["Nachname"])
                all_roles = sorted(df["Rolle"].unique().tolist() + ["admin","user","inventur","barlead"])
                # Duplizierte Einträge bereinigen
                all_roles = sorted(set(all_roles))
                e_role = st.selectbox("Rolle", all_roles, index=all_roles.index(row["Rolle"]) if row["Rolle"] in all_roles else 0)
                e_funcs = st.multiselect(
                    "Funktionen", func_list,
                    default=[f.strip() for f in (row["Funktionen"] or "").split(",") if f.strip()]
                )

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
            email    = c2.text_input("E-Mail")
            c3, c4 = st.columns(2)
            first_name = c3.text_input("Vorname")
            last_name  = c4.text_input("Nachname")
            role = st.selectbox("Rolle", ["admin", "barlead", "user", "inventur"], index=2)
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
                                INSERT INTO users(username, email, first_name, last_name, role, functions, passhash, created_at)
                                VALUES(?,?,?,?,?,?, '', datetime('now'))
                            """, (username, email, first_name, last_name, role, ", ".join(selected_funcs)))
                            cn.commit()
                        st.success(f"Benutzer '{username}' angelegt.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fehler beim Anlegen: {e}")

    # ------------------- TAB 3: Suche -------------------
    with tabs[2]:
        st.subheader("Benutzer suchen & bearbeiten")
        query = st.text_input("Suchbegriff (Name, E-Mail, Rolle, Funktionen …)")
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
                st.dataframe(df.drop(columns=["ID"]), use_container_width=True, height=300)
                sel = st.selectbox("Benutzer auswählen", df["Benutzername"])
                if sel:
                    row = df[df["Benutzername"] == sel].iloc[0]
                    # Rollenliste dynamisch + Defaults
                    all_roles = sorted(set(list(df["Rolle"].unique()) + ["admin","user","inventur","barlead"]))
                    new_role = st.selectbox("Neue Rolle", all_roles, index=all_roles.index(row["Rolle"]) if row["Rolle"] in all_roles else 0)
                    with conn() as cn:
                        c = cn.cursor()
                        func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]
                    new_funcs = st.multiselect("Funktionen", func_list, default=[f.strip() for f in (row["Funktionen"] or "").split(",") if f.strip()])
                    if st.button("💾 Änderungen speichern", key="search_edit"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("UPDATE users SET role=?, functions=? WHERE id=?", (new_role, ", ".join(new_funcs), int(row["ID"])))
                            cn.commit()
                        st.success("Benutzer aktualisiert.")
                        st.rerun()
            else:
                st.info("Keine Benutzer gefunden.")

    # ------------------- TAB 4: Funktionen -------------------
    with tabs[3]:
        st.subheader("Funktionen verwalten")
        with conn() as cn:
            c = cn.cursor()
            funcs = c.execute("SELECT id, name, description FROM functions ORDER BY name").fetchall()

        df = pd.DataFrame(funcs, columns=["ID", "Funktion", "Beschreibung"])
        edited = st.data_editor(
            df.drop(columns=["ID"]),
            use_container_width=True,
            num_rows="dynamic",
            height=400
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
