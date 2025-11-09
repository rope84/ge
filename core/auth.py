# core/auth.py
import re
import hashlib
import streamlit as st
from datetime import datetime
from typing import Optional, Dict, Tuple
from core.db import conn
from core.config import APP_NAME, APP_VERSION

# simple Policy: min 6, 1 Großbuchstabe, 1 Sonderzeichen
PWD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{6,}$")

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def verify_pw(pw: str, ph: str) -> bool:
    if not ph:
        return False
    return hash_pw(pw) == ph

def _role_from_functions(functions: str) -> str:
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    if "admin" in funcs or "betriebsleiter" in funcs:
        return "admin"
    return "user"

# -------- Schema-Sicherung (Create/Migrate) --------
def ensure_user_schema():
    """
    Stellt sicher, dass es die Tabelle 'users' mit allen benötigten Spalten gibt.
    Fehlen Spalten, werden sie via ALTER TABLE hinzugefügt.
    """
    required_cols = {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "username": "TEXT NOT NULL",
        "passhash": "TEXT",
        "role": "TEXT",            # Legacy-Kompatibilität
        "scope": "TEXT",           # Legacy-Kompatibilität
        "functions": "TEXT",
        "email": "TEXT",
        "first_name": "TEXT",
        "last_name": "TEXT",
        "created_at": "TEXT",
    }

    with conn() as cn:
        c = cn.cursor()
        # Gibt es die Tabelle?
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        exists = c.fetchone() is not None

        if not exists:
            # Neu anlegen mit vollständigem Schema
            cols_sql = ", ".join([f"{k} {v}" for k, v in required_cols.items()])
            c.execute(f"CREATE TABLE users ({cols_sql})")
            # UNIQUE-Index auf username
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users(username)")
            cn.commit()
            return

        # Tabelle existiert -> fehlende Spalten ergänzen
        current = {row[1] for row in c.execute("PRAGMA table_info(users)")}
        for col, decl in required_cols.items():
            if col not in current:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
        # Index sicherstellen
        c.execute("""
            SELECT name FROM sqlite_master
             WHERE type='index' AND name='ux_users_username'
        """)
        if c.fetchone() is None:
            try:
                c.execute("CREATE UNIQUE INDEX ux_users_username ON users(username)")
            except Exception:
                pass
        cn.commit()

# -------- Seeding & Konsistenz --------
def seed_admin_if_empty():
    ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n == 0:
            c.execute("""
                INSERT INTO users(username, email, first_name, last_name, passhash, functions, role, scope, created_at)
                VALUES(?,?,?,?,?,?,?,?,datetime('now'))
            """, (
                "oklub",
                "admin@oklub.at",
                "OKlub",
                "Admin",
                hash_pw("OderKlub!"),
                "Admin",
                "admin",   # legacy role befüllen
                "Admin",   # legacy scope befüllen
            ))
            cn.commit()

def ensure_admin_consistency():
    """
    - Stellt sicher, dass 'functions' existiert und der User 'oklub' Admin-Rechte hat.
    - Hält legacy 'role' im Einklang mit 'functions'.
    """
    ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        # functions sicher für oklub
        c.execute("""
            UPDATE users
               SET functions = CASE WHEN TRIM(COALESCE(functions,''))='' THEN 'Admin' ELSE functions END
             WHERE username='oklub'
        """)
        # legacy role entsprechend setzen
        c.execute("""
            UPDATE users
               SET role = CASE
                            WHEN LOWER(COALESCE(functions,'')) LIKE '%admin%' OR
                                 LOWER(COALESCE(functions,'')) LIKE '%betriebsleiter%'
                            THEN 'admin'
                            ELSE 'user'
                          END
             WHERE username='oklub'
        """)
        cn.commit()

# -------- User-Funktionen --------
def _fetch_user(username: str) -> Optional[Dict]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id, username, email, first_name, last_name, passhash, functions, role, scope, created_at
              FROM users
             WHERE username=?
        """, (username.strip(),)).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "email": row[2] or "",
        "first_name": row[3] or "",
        "last_name": row[4] or "",
        "passhash": row[5] or "",
        "functions": row[6] or "",
        "role": row[7] or "",
        "scope": row[8] or "",
        "created_at": row[9] or "",
    }

def _set_passhash(user_id: int, ph: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE users SET passhash=? WHERE id=?", (ph, user_id))
        cn.commit()

def _do_login(user: str, pw: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Rückgabe: (ok, role, functions)
    """
    ensure_user_schema()
    u = _fetch_user(user)
    if not u:
        return (False, None, None)

    # First login: noch kein Passwort gesetzt -> jetzt setzen
    if not u["passhash"]:
        if not pw:
            return (False, None, None)
        _set_passhash(u["id"], hash_pw(pw))
        u["passhash"] = hash_pw(pw)

    if not verify_pw(pw, u["passhash"]):
        return (False, None, None)

    role = _role_from_functions(u["functions"]) or (u["role"] or "user")

    # Session-State füllen
    st.session_state.auth = True
    st.session_state.username   = u["username"]
    st.session_state.role       = role
    st.session_state.scope      = u["functions"] or u["scope"] or ""
    st.session_state.email      = u["email"]
    st.session_state.first_name = u["first_name"]
    st.session_state.last_name  = u["last_name"]
    st.session_state.login_ts   = datetime.utcnow().isoformat()

    return (True, role, u["functions"])

def login_required(app_name: str, app_version: str):
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.caption(app_version)
    st.subheader("Login")

    u = st.text_input("Benutzername", key="lr_user")
    p = st.text_input("Passwort", type="password", key="lr_pw")

    c1, c2 = st.columns([2,1])
    if c1.button("Anmelden", use_container_width=True):
        ok, _, _ = _do_login(u, p)
        if not ok:
            st.error("Falscher Benutzername oder Passwort.")

    if c2.button("Passwort zurücksetzen", use_container_width=True):
        st.info("Bitte kontaktieren Sie den Administrator: admin@o-der-klub.at")

def change_password(username: str, old_pw: str, new_pw: str) -> tuple[bool, str]:
    if not PWD_PATTERN.match(new_pw):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT passhash FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return False, "Benutzer nicht gefunden."
        if not verify_pw(old_pw, row[0] or ""):
            return False, "Altes Passwort stimmt nicht."
        c.execute("UPDATE users SET passhash=? WHERE username=?", (hash_pw(new_pw), username))
        cn.commit()
    return True, "Passwort aktualisiert."

def admin_set_password(username: str, new_pw: str) -> tuple[bool, str]:
    if not PWD_PATTERN.match(new_pw):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."
    with conn() as cn:
        c = cn.cursor()
        if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return False, "Benutzer nicht gefunden."
        c.execute("UPDATE users SET passhash=? WHERE username=?", (hash_pw(new_pw), username))
        cn.commit()
    return True, "Passwort gesetzt."
