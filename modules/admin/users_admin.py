import streamlit as st
import pandas as pd
from typing import List, Tuple
from core.db import conn
from core.ui_theme import section_title

try:
    from core.auth import change_password
except Exception:
    change_password = None

# ------------------------------------------------------------
# SCHEMA-HELPERS
# ------------------------------------------------------------

PERM_COLS: List[Tuple[str, str]] = [
    ("can_view_sales", "INTEGER NOT NULL DEFAULT 0"),
    ("can_edit_sales", "INTEGER NOT NULL DEFAULT 0"),
    ("can_view_inventory", "INTEGER NOT NULL DEFAULT 0"),
    ("can_edit_inventory", "INTEGER NOT NULL DEFAULT 0"),
]

def _ensure_user_schema():
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
        # Migration
        c.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in c.fetchall()}
        if "functions" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN functions TEXT DEFAULT ''")
        if "passhash" not in cols:
            # wichtig: NOT NULL **mit** DEFAULT, sonst schlägt ALTER TABLE fehl
            c.execute("ALTER TABLE users ADD COLUMN passhash TEXT NOT NULL DEFAULT ''")
        if "created_at" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN created_at TEXT")

        # Normalisieren / Backfill
        c.execute("UPDATE users SET passhash = COALESCE(passhash, '')")
        c.execute("UPDATE users SET created_at = COALESCE(created_at, datetime('now'))")
        cn.commit()

def _ensure_function_schema():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS functions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT
            )
        """)
        c.execute("PRAGMA table_info(functions)")
        cols = {row[1] for row in c.fetchall()}
        for col_name, col_def in PERM_COLS:
            if col_name not in cols:
                c.execute(f"ALTER TABLE functions ADD COLUMN {col_name} {col_def}")
        set_expr = ", ".join([f"{col}=COALESCE({col},0)" for col, _ in PERM_COLS])
        c.execute(f"UPDATE functions SET {set_expr}")
        cn.commit()

def _get_roles_counts():
    with conn() as cn:
        c = cn.cursor()
        return c.execute("SELECT role, COUNT(*) FROM users GROUP BY role").fetchall()

def _get_functions_list():
    with conn() as cn:
        c = cn.cursor()
        return [r[0] for r in c.execute("SELECT name FROM functions ORDER BY name").fetchall()]

def _count_users_with_function(func_name: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        sql = """
            SELECT COUNT(*) FROM users
            WHERE (','||LOWER(COALESCE(functions,''))||',') LIKE '%,'||LOWER(?)||',%'
        """
        return c.execute(sql, (func_name,)).fetchone()[0]

# ------------------------------------------------------------
# UI-HELPERS
# ------------------------------------------------------------

def _card_html(title: str, color: str, lines: List[str]) -> str:
    body = "<br/>".join(
        [f"<span style='opacity:0.85;font-size:12px;'>{ln}</span>" for ln in lines]
    )
    return f"""
    <div style="
        display:flex; gap:12px; align-items:flex-start;
        padding:12px 14px; border-radius:14px;
        background:rgba(255,255,255,0.03);
        box-shadow:0 6px 16px rgba(0,0,0,0.15);
        position:relative; overflow:hidden;
    ">
      <div style="
        position:absolute; left:0; top:0; bottom:0; width:6px;
        background: linear-gradient(180deg, {color}, {color}55);
        border-top-left-radius:14px; border-bottom-left-radius:14px;
      "></div>
      <div style="font-size:13px;">
        <b>{title}</b><br/>{body}
      </div>
    </div>
    """

# ------------------------------------------------------------
# TAB 1 – ÜBERSICHT (modernes Design)
# ------------------------------------------------------------

def _tab_overview():
    roles = _get_roles_counts()
    total = sum([r[1] for r in roles]) if roles else 0

    c1, c2, c3, c4 = st.columns(4, gap="large")
    c1.markdown(
        _card_html("👥 Gesamt", "#3b82f6", [f"Alle Benutzer: <b>{total}</b>"]),
        unsafe_allow_html=True,
    )

    if roles:
        for i, (role, count) in enumerate(sorted(roles, key=lambda x: x[0])):
            color = {
                "admin": "#ef4444",
                "barlead": "#0ea5e9",
                "user": "#10b981",
                "inventur": "#f59e0b",
            }.get(role.lower(), "#6b7280")
            col = [c2, c3, c4, c1][i % 4]
            col.markdown(
                _card_html(role.capitalize(), color, [f"Benutzer: <b>{count}</b>"]),
                unsafe_allow_html=True,
            )
    else:
        st.info("Noch keine Benutzer vorhanden.")

# ------------------------------------------------------------
# TAB 2 – USER ERSTELLEN
# ------------------------------------------------------------

def _tab_create_user():
    section_title("➕ User erstellen")
    func_list = _get_functions_list()

    with st.form("ua_add_user_form"):
        c1, c2 = st.columns(2)
        username = c1.text_input("Benutzername")
        email = c2.text_input("E-Mail")

        c3, c4 = st.columns(2)
        first_name = c3.text_input("Vorname")
        last_name = c4.text_input("Nachname")

        role = st.selectbox("Rolle", ["admin", "barlead", "user", "inventur"], index=2)
        selected_funcs = st.multiselect("Funktionen", func_list)
        password = st.text_input("Passwort (optional)", type="password")

        if st.form_submit_button("👤 User anlegen", use_container_width=True):
    if not username:
        st.warning("Benutzername ist erforderlich.")
        return
    try:
        with conn() as cn:
            c = cn.cursor()
            c.execute("""
                INSERT INTO users (username, email, first_name, last_name, role, functions, passhash)
                VALUES (?,?,?,?,?,?,?)
            """, (username, email, first_name, last_name, role, ", ".join(selected_funcs), ""))
            cn.commit()

        # Passwort (optional) setzen – hash via core.auth.change_password
        if password and change_password:
            try:
                change_password(username, password)
            except Exception:
                pass

        st.success(f"User '{username}' angelegt.")
        st.rerun()
    except Exception as e:
        st.error(f"Fehler beim Anlegen: {e}")

# ------------------------------------------------------------
# TAB 3 – SUCHEN & BEARBEITEN
# ------------------------------------------------------------

ALPHABET = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

def _alpha_selector():
    st.caption("Filter nach Anfangsbuchstabe (Vorname / Nachname / Benutzername)")
    cols = st.columns(13)
    sel = st.session_state.get("ua_alpha", None)
    for i, letter in enumerate(ALPHABET[:13]):
        if cols[i].button(letter, key=f"ua_alpha_btn_{letter}"):
            st.session_state["ua_alpha"] = letter
            st.rerun()
    cols2 = st.columns(13)
    for i, letter in enumerate(ALPHABET[13:]):
        if cols2[i].button(letter, key=f"ua_alpha_btn_{letter}"):
            st.session_state["ua_alpha"] = letter
            st.rerun()
    if st.button("Alle", key="ua_alpha_clear"):
        st.session_state["ua_alpha"] = None
        st.rerun()
    return sel

def _search_users(q: str, alpha: str):
    with conn() as cn:
        c = cn.cursor()
        if q:
            like = f"%{q}%"
            sql = """
                SELECT id, username, email, first_name, last_name, role, functions
                FROM users
                WHERE username LIKE ? OR email LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR role LIKE ? OR functions LIKE ?
                ORDER BY username
            """
            return c.execute(sql, (like, like, like, like, like, like)).fetchall()
        elif alpha:
            sql = """
                SELECT id, username, email, first_name, last_name, role, functions
                FROM users
                WHERE (first_name IS NOT NULL AND UPPER(SUBSTR(first_name,1,1)) = ?)
                   OR (last_name  IS NOT NULL AND UPPER(SUBSTR(last_name ,1,1)) = ?)
                   OR (username   IS NOT NULL AND UPPER(SUBSTR(username  ,1,1)) = ?)
                ORDER BY username
            """
            return c.execute(sql, (alpha, alpha, alpha)).fetchall()
        return []

def _edit_user_card(row, func_list):
    uid, uname, email, first, last, role, funcs = row
    with st.container(border=True):
        st.markdown(f"**{uname}** · Rolle: `{role}`")
        c1, c2 = st.columns(2)
        e_first = c1.text_input("Vorname", first or "", key=f"ua_first_{uid}")
        e_last  = c2.text_input("Nachname", last or "", key=f"ua_last_{uid}")
        e_mail  = st.text_input("E-Mail", email or "", key=f"ua_mail_{uid}")

        e_role = st.selectbox("Rolle", ["admin","barlead","user","inventur"],
                              index=["admin","barlead","user","inventur"].index(role)
                              if role in ["admin","barlead","user","inventur"] else 2,
                              key=f"ua_role_{uid}")
        curr_funcs = [f.strip() for f in (funcs or "").split(",") if f.strip()]
        e_funcs = st.multiselect("Funktionen", func_list, default=curr_funcs, key=f"ua_funcs_{uid}")

        colA, colB = st.columns([1,1])
        if colA.button("💾 Speichern", key=f"ua_save_{uid}", use_container_width=True):
            with conn() as cn:
                c = cn.cursor()
                c.execute("""
                    UPDATE users SET first_name=?, last_name=?, email=?, role=?, functions=? WHERE id=?
                """, (e_first, e_last, e_mail, e_role, ", ".join(e_funcs), uid))
                cn.commit()
            st.success("Änderungen gespeichert.")
            st.rerun()

        confirm = colB.checkbox("Löschen bestätigen", key=f"ua_del_conf_{uid}")
        if colB.button("🗑️ Löschen", key=f"ua_del_{uid}", use_container_width=True, disabled=not confirm):
            with conn() as cn:
                c = cn.cursor()
                c.execute("DELETE FROM users WHERE id=?", (uid,))
                cn.commit()
            st.warning(f"User '{uname}' gelöscht.")
            st.rerun()

def _tab_search_edit():
    section_title("🔎 Suchen & Bearbeiten")
    q = st.text_input("Suchbegriff (Name, E-Mail, Rolle, Funktionen …)", key="ua_q")
    alpha = _alpha_selector()
    results = _search_users(q.strip(), alpha)
    if not results:
        st.info("Keine Treffer.")
        return
    func_list = _get_functions_list()
    usernames = [r[1] for r in results]
    sel = st.selectbox("Benutzer auswählen", usernames, key="ua_sel_user")
    row = next((r for r in results if r[1] == sel), None)
    if row:
        _edit_user_card(row, func_list)

# ------------------------------------------------------------
# TAB 4 – FUNKTIONEN & RECHTE
# ------------------------------------------------------------

def _tab_functions():
    section_title("⚙️ Funktionen & Rechte")

    with conn() as cn:
        c = cn.cursor()
        funcs = c.execute("""
            SELECT id, name, description,
                   COALESCE(can_view_sales,0), COALESCE(can_edit_sales,0),
                   COALESCE(can_view_inventory,0), COALESCE(can_edit_inventory,0)
            FROM functions ORDER BY name
        """).fetchall()

    for fid, name, desc, v_s, e_s, v_i, e_i in funcs:
        users_with = _count_users_with_function(name)
        with st.expander(f"{name} · {users_with} User", expanded=False):
            c1, c2 = st.columns([2, 1])
            e_name = c1.text_input("Funktionsname", name, key=f"fn_name_{fid}", disabled=(name.lower()=="admin"))
            e_desc = c1.text_input("Beschreibung", desc or "", key=f"fn_desc_{fid}")

            box = c2.container(border=True)
            box.caption("Rechte")
            nv1 = box.checkbox("Umsätze ansehen", v_s==1, key=f"fn_vsales_{fid}")
            ne1 = box.checkbox("Umsätze bearbeiten", e_s==1, key=f"fn_esales_{fid}")
            nv2 = box.checkbox("Inventur ansehen", v_i==1, key=f"fn_vinv_{fid}")
            ne2 = box.checkbox("Inventur bearbeiten", e_i==1, key=f"fn_einv_{fid}")

            colS, colD = st.columns([1,1])
            if colS.button("💾 Speichern", key=f"fn_save_{fid}", use_container_width=True):
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("""
                        UPDATE functions SET name=?, description=?,
                        can_view_sales=?, can_edit_sales=?, can_view_inventory=?, can_edit_inventory=? WHERE id=?
                    """, (e_name.strip(), e_desc.strip(), int(nv1), int(ne1), int(nv2), int(ne2), fid))
                    cn.commit()
                st.success("Gespeichert.")
                st.rerun()

            can_delete = (name.lower() != "admin")
            confirm = colD.checkbox("Löschen bestätigen", key=f"fn_del_conf_{fid}", disabled=not can_delete)
            if colD.button("🗑️ Löschen", key=f"fn_del_{fid}", disabled=(not can_delete or not confirm), use_container_width=True):
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("DELETE FROM functions WHERE id=?", (fid,))
                    cn.commit()
                st.warning(f"Funktion '{name}' gelöscht.")
                st.rerun()

    st.divider()
    with st.form("fn_add"):
        st.subheader("Neue Funktion anlegen")
        c1, c2 = st.columns([2,1])
        n_name = c1.text_input("Funktionsname")
        n_desc = c1.text_input("Beschreibung")
        box = c2.container(border=True)
        box.caption("Rechte")
        nv1 = box.checkbox("Umsätze ansehen", key="fn_new_vsales")
        ne1 = box.checkbox("Umsätze bearbeiten", key="fn_new_esales")
        nv2 = box.checkbox("Inventur ansehen", key="fn_new_vinv")
        ne2 = box.checkbox("Inventur bearbeiten", key="fn_new_einv")
        if st.form_submit_button("➕ Funktion hinzufügen", use_container_width=True):
            if not n_name or n_name.strip().lower() == "admin":
                st.warning("Ungültiger Funktionsname.")
            else:
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("""
                        INSERT INTO functions (name, description, can_view_sales, can_edit_sales, can_view_inventory, can_edit_inventory)
                        VALUES (?,?,?,?,?,?)
                    """, (n_name.strip(), n_desc.strip(), int(nv1), int(ne1), int(nv2), int(ne2)))
                    cn.commit()
                st.success("Funktion angelegt.")
                st.rerun()

# ------------------------------------------------------------
# ENTRY
# ------------------------------------------------------------

def render_users_admin():
    _ensure_user_schema()
    _ensure_function_schema()

    tabs = st.tabs([
        "📊 Übersicht",
        "➕ User erstellen",
        "🔎 Suchen & Bearbeiten",
        "⚙️ Funktionen"
    ])
    with tabs[0]: _tab_overview()
    with tabs[1]: _tab_create_user()
    with tabs[2]: _tab_search_edit()
    with tabs[3]: _tab_functions()
