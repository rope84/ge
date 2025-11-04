import streamlit as st
import pandas as pd
from core.db import conn

# --- Style-Helper (Card, Farben etc.) ---
def _role_color(role: str) -> str:
    colors = {
        "admin": "#e11d48",
        "barlead": "#0ea5e9",
        "user": "#10b981",
        "inventur": "#f59e0b",
    }
    return colors.get(role, "#6b7280")

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

    tabs = st.tabs(["📊 Übersicht", "👤 Benutzer", "🔍 Suchen & Bearbeiten", "⚙️ Funktionen"])

    # ---------------- TAB 1: Übersicht ----------------
    with tabs[0]:
        with conn() as cn:
            c = cn.cursor()
            total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            rows  = c.execute("SELECT role, COUNT(*) FROM users GROUP BY role ORDER BY role").fetchall()

        col_total = st.columns(1)[0]
        col_total.markdown(_card("Gesamtanzahl Benutzer", str(total), "#3b82f6"), unsafe_allow_html=True)
        st.write("")

        if rows:
            def chunk(lst, n):
                for i in range(0, len(lst), n):
                    yield lst[i:i+n]
            for group in chunk(rows, 4):
                cols = st.columns(len(group))
                for (role, count), col in zip(group, cols):
                    col.markdown(_card(f"Rolle: {role}", str(count), _role_color(role)), unsafe_allow_html=True)
        else:
            st.info("Noch keine Benutzer vorhanden.")

    # ---------------- TAB 2: Benutzer anlegen ----------------
    with tabs[1]:
        st.subheader("Neuen Benutzer anlegen")

        with conn() as cn:
            c = cn.cursor()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

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

            if st.form_submit_button("➕ User anlegen", use_container_width=True, key="create_user"):
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

    # ---------------- TAB 3: Suchen & Bearbeiten ----------------
    with tabs[2]:
        st.subheader("Benutzer suchen & bearbeiten")

        col1, col2 = st.columns([3, 2])
        query = col1.text_input("Suchbegriff (Name, E-Mail, Rolle, Funktionen …)")
        letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        selected_letter = col2.selectbox("Nach Anfangsbuchstaben filtern", ["—"] + letters)

        where_clause = ""
        params = []

        if query:
            where_clause = """WHERE username LIKE ? OR email LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR role LIKE ? OR functions LIKE ?"""
            params = [f"%{query}%"] * 6
        elif selected_letter and selected_letter != "—":
            letter = selected_letter + "%"
            where_clause = """WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?"""
            params = [letter, letter, letter]

        # Funktionsliste laden
        with conn() as cn:
            c = cn.cursor()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

        if where_clause:
            with conn() as cn:
                c = cn.cursor()
                results = c.execute(f"""
                    SELECT id, username, email, first_name, last_name, role, functions
                    FROM users
                    {where_clause}
                    ORDER BY username
                """, tuple(params)).fetchall()

            if results:
                usernames = [r[1] for r in results]
                sel_user = st.selectbox("Benutzer auswählen", usernames)

                if sel_user:
                    row = next(r for r in results if r[1] == sel_user)
                    uid, username, email, first, last, role, funcs = row

                    st.markdown("---")
                    st.markdown(
                        f"""
                        <div style='padding:16px; border-radius:12px; background:rgba(255,255,255,0.04);
                        box-shadow:0 4px 12px rgba(0,0,0,0.2); margin-bottom:18px;'>
                            <h4 style='margin:0;'>🧑‍💻 {username}</h4>
                            <p style='margin-top:2px; opacity:0.8; font-size:13px;'>
                                Rolle: <b>{role}</b> &nbsp; | &nbsp; Angelegt am: <i>{uid}</i>
                            </p>
                        </div>
                        """, unsafe_allow_html=True
                    )

                    with st.form(f"edit_user_{uid}"):
                        e1, e2 = st.columns(2)
                        e_email = e1.text_input("E-Mail", email)
                        e_role  = e2.selectbox(
                            "Rolle",
                            ["admin", "barlead", "user", "inventur"],
                            index=["admin","barlead","user","inventur"].index(role) if role in ["admin","barlead","user","inventur"] else 2,
                            key=f"role_{uid}"
                        )
                        e3, e4 = st.columns(2)
                        e_first = e3.text_input("Vorname", first or "")
                        e_last  = e4.text_input("Nachname", last or "")
                        e_funcs = st.multiselect(
                            "Funktionen",
                            func_list,
                            default=[f.strip() for f in (funcs or "").split(",") if f.strip()],
                            key=f"funcs_{uid}"
                        )

                        save_btn, del_btn = st.columns([2, 1])

                        if save_btn.form_submit_button("💾 Änderungen speichern", use_container_width=True, key=f"save_{uid}"):
                            try:
                                with conn() as cn:
                                    c = cn.cursor()
                                    c.execute("""
                                        UPDATE users
                                        SET email=?, first_name=?, last_name=?, role=?, functions=?
                                        WHERE id=?
                                    """, (e_email, e_first, e_last, e_role, ", ".join(e_funcs), uid))
                                    cn.commit()
                                st.success("✅ Benutzer aktualisiert.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Fehler beim Speichern: {e}")

                    with st.expander("❌ Benutzer löschen", expanded=False):
                        st.warning("Achtung: Das Löschen ist endgültig!")
                        confirm = st.checkbox("Löschen bestätigen", key=f"confirm_{uid}")
                        if st.button("🗑️ Benutzer jetzt löschen", use_container_width=True, disabled=not confirm, key=f"delete_{uid}"):
                            try:
                                with conn() as cn:
                                    c = cn.cursor()
                                    c.execute("DELETE FROM users WHERE id=?", (uid,))
                                    cn.commit()
                                st.success(f"Benutzer '{username}' gelöscht.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Fehler beim Löschen: {e}")
            else:
                st.info("Keine Benutzer gefunden.")
        else:
            st.caption("🔎 Bitte Suchbegriff eingeben oder Buchstaben auswählen.")

    # ---------------- TAB 4: Funktionen ----------------
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

        if st.button("💾 Änderungen speichern", use_container_width=True, key="funcs_save"):
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
