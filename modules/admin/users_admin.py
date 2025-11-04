import streamlit as st
import pandas as pd
from core.db import conn


# --- Hilfsfunktionen & Styles ---
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
            username TEXT NOT NULL UNIQUE,
            email TEXT,
            first_name TEXT,
            last_name TEXT,
            role TEXT NOT NULL,
            functions TEXT DEFAULT '',
            passhash TEXT NOT NULL DEFAULT '',
            created_at TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            can_view_sales INTEGER DEFAULT 0,
            can_edit_sales INTEGER DEFAULT 0,
            can_view_inventory INTEGER DEFAULT 0,
            can_edit_inventory INTEGER DEFAULT 0
        )
        """)
        # Standard Adminfunktion
        if c.execute("SELECT COUNT(*) FROM functions WHERE name='Admin'").fetchone()[0] == 0:
            c.execute("INSERT INTO functions(name, description, can_view_sales, can_edit_sales, can_view_inventory, can_edit_inventory) VALUES('Admin', 'Vollzugriff', 1,1,1,1)")
        cn.commit()


# --- Haupt-UI ---
def render_users_admin():
    _ensure_tables()

    tabs = st.tabs(["📊 Übersicht", "🧩 User erstellen", "🔍 Suchen & Bearbeiten", "⚙️ Rollen & Rechte"])

    # ---------- TAB 1: Übersicht ----------
    with tabs[0]:
        with conn() as cn:
            c = cn.cursor()
            total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            rows = c.execute("SELECT role, COUNT(*) FROM users GROUP BY role ORDER BY role").fetchall()

        st.markdown(_card("Gesamtanzahl User", str(total), "#3b82f6"), unsafe_allow_html=True)
        st.write("")

        if rows:
            for role, count in rows:
                st.markdown(_card(f"Rolle: {role}", str(count), _role_color(role)), unsafe_allow_html=True)
        else:
            st.info("Noch keine User vorhanden.")

    # ---------- TAB 2: User erstellen ----------
    with tabs[1]:
        st.subheader("Neuen User erstellen")

        with conn() as cn:
            c = cn.cursor()
            func_list = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

        with st.form("add_user_form"):
            c1, c2 = st.columns(2)
            username = c1.text_input("Benutzername")
            email = c2.text_input("E-Mail")
            c3, c4 = st.columns(2)
            first = c3.text_input("Vorname")
            last = c4.text_input("Nachname")
            role = st.selectbox("Rolle", ["admin", "barlead", "user", "inventur"], index=2)
            funcs = st.multiselect("Zugeordnete Funktion(en)", func_list)
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
                            """, (username, email, first, last, role, ", ".join(funcs)))
                            cn.commit()
                        st.success(f"User '{username}' wurde erstellt.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fehler beim Anlegen: {e}")

    # ---------- TAB 3: Suchen & Bearbeiten ----------
    with tabs[2]:
        st.subheader("User suchen & bearbeiten")

        col1, col2 = st.columns([3, 2])
        query = col1.text_input("Suchbegriff (Name, E-Mail, Rolle …)")
        letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        sel_letter = col2.selectbox("Nach Buchstaben filtern", ["—"] + letters)

        where = ""
        params = []
        if query:
            where = """WHERE username LIKE ? OR email LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR role LIKE ? OR functions LIKE ?"""
            params = [f"%{query}%"] * 6
        elif sel_letter != "—":
            letter = sel_letter + "%"
            where = """WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?"""
            params = [letter, letter, letter]

        if where:
            with conn() as cn:
                c = cn.cursor()
                res = c.execute(f"SELECT id, username, email, first_name, last_name, role, functions FROM users {where} ORDER BY username", tuple(params)).fetchall()

            if res:
                usernames = [r[1] for r in res]
                sel_user = st.selectbox("User auswählen", usernames)

                if sel_user:
                    row = next(r for r in res if r[1] == sel_user)
                    uid, uname, email, first, last, role, funcs = row
                    funcs_list = [f.strip() for f in (funcs or '').split(',') if f.strip()]

                    st.markdown("---")
                    st.markdown(f"### 🧑‍💻 {uname}")
                    st.caption(f"Rolle: **{role}**  |  ID: {uid}")

                    with st.form(f"edit_{uid}"):
                        e1, e2 = st.columns(2)
                        new_email = e1.text_input("E-Mail", email)
                        new_role = e2.selectbox("Rolle", ["admin", "barlead", "user", "inventur"], index=["admin","barlead","user","inventur"].index(role))
                        e3, e4 = st.columns(2)
                        new_first = e3.text_input("Vorname", first or "")
                        new_last = e4.text_input("Nachname", last or "")

                        with conn() as cn:
                            c = cn.cursor()
                            all_funcs = [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]
                        new_funcs = st.multiselect("Zugeordnete Funktion(en)", all_funcs, default=funcs_list)

                        save_col, del_col = st.columns([2,1])
                        if save_col.form_submit_button("💾 Änderungen speichern", key=f"save_{uid}"):
                            with conn() as cn:
                                c = cn.cursor()
                                c.execute("""UPDATE users SET email=?, first_name=?, last_name=?, role=?, functions=? WHERE id=?""",
                                          (new_email, new_first, new_last, new_role, ", ".join(new_funcs), uid))
                                cn.commit()
                            st.success("Änderungen gespeichert.")
                            st.rerun()

                    with st.expander("🗑️ User löschen", expanded=False):
                        st.warning("⚠️ Dieser Vorgang kann nicht rückgängig gemacht werden!")
                        confirm = st.checkbox("Löschen bestätigen", key=f"del_conf_{uid}")
                        if st.button("❌ Jetzt löschen", disabled=not confirm, key=f"del_{uid}"):
                            with conn() as cn:
                                c = cn.cursor()
                                c.execute("DELETE FROM users WHERE id=?", (uid,))
                                cn.commit()
                            st.success(f"User '{uname}' wurde gelöscht.")
                            st.rerun()
            else:
                st.info("Keine User gefunden.")
        else:
            st.caption("🔎 Bitte Suchbegriff eingeben oder Buchstaben auswählen.")

    # ---------- TAB 4: Rollen & Rechte ----------
    with tabs[3]:
        st.subheader("Rollen & Rechte verwalten")

        with conn() as cn:
            c = cn.cursor()
            functions = c.execute("""
                SELECT id, name, description, can_view_sales, can_edit_sales, can_view_inventory, can_edit_inventory
                FROM functions ORDER BY name
            """).fetchall()

        # Bestehende Rollen anzeigen
        for fid, name, desc, v_sales, e_sales, v_inv, e_inv in functions:
            with st.expander(f"🎯 {name}", expanded=False):
                col_info, col_actions = st.columns([3,1])
                col_info.text_area("Beschreibung", desc or "", key=f"desc_{fid}")
                rights = {
                    "Umsätze ansehen": v_sales,
                    "Umsätze bearbeiten": e_sales,
                    "Inventur ansehen": v_inv,
                    "Inventur bearbeiten": e_inv
                }
                st.write("**Rechte:**")
                new_vals = {}
                for label, val in rights.items():
                    new_vals[label] = st.checkbox(label, value=bool(val), key=f"{label}_{fid}")

                # Anzahl User dieser Rolle anzeigen
                with conn() as cn:
                    c = cn.cursor()
                    count = c.execute("SELECT COUNT(*) FROM users WHERE functions LIKE ?", (f"%{name}%",)).fetchone()[0]
                st.caption(f"👥 Zugeordnete User: {count}")

                if name != "Admin":
                    save_col, del_col = st.columns([2,1])
                    if save_col.button("💾 Änderungen speichern", key=f"save_func_{fid}"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("""
                                UPDATE functions
                                SET description=?, can_view_sales=?, can_edit_sales=?, can_view_inventory=?, can_edit_inventory=?
                                WHERE id=?
                            """, (
                                st.session_state[f"desc_{fid}"],
                                int(new_vals["Umsätze ansehen"]),
                                int(new_vals["Umsätze bearbeiten"]),
                                int(new_vals["Inventur ansehen"]),
                                int(new_vals["Inventur bearbeiten"]),
                                fid
                            ))
                            cn.commit()
                        st.success(f"Funktion '{name}' aktualisiert.")
                        st.rerun()

                    if del_col.button("🗑️ Löschen", key=f"del_func_{fid}"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("DELETE FROM functions WHERE id=?", (fid,))
                            cn.commit()
                        st.warning(f"Funktion '{name}' gelöscht.")
                        st.rerun()
                else:
                    st.info("Admin-Rolle kann nicht geändert oder gelöscht werden.")

        st.markdown("---")
        st.subheader("➕ Neue Funktion hinzufügen")
        with st.form("new_func_form"):
            nf_name = st.text_input("Funktionsname")
            nf_desc = st.text_area("Beschreibung")
            st.markdown("**Rechte:**")
            nf_v_sales = st.checkbox("Umsätze ansehen", value=False)
            nf_e_sales = st.checkbox("Umsätze bearbeiten", value=False)
            nf_v_inv = st.checkbox("Inventur ansehen", value=False)
            nf_e_inv = st.checkbox("Inventur bearbeiten", value=False)
            if st.form_submit_button("➕ Funktion hinzufügen", key="add_func"):
                if nf_name.strip():
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("""
                            INSERT INTO functions(name, description, can_view_sales, can_edit_sales, can_view_inventory, can_edit_inventory)
                            VALUES(?,?,?,?,?,?)
                        """, (nf_name.strip(), nf_desc.strip(), int(nf_v_sales), int(nf_e_sales), int(nf_v_inv), int(nf_e_inv)))
                        cn.commit()
                    st.success(f"Neue Funktion '{nf_name}' wurde hinzugefügt.")
                    st.rerun()
                else:
                    st.warning("Bitte einen Namen angeben.")
