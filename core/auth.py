# core/auth.py
import re
import hashlib
import streamlit as st
from datetime import datetime
from typing import Optional, Dict, Tuple, List
from core.db import conn
from core.config import APP_NAME, APP_VERSION

# simple Policy: min 6, 1 Großbuchstabe, 1 Sonderzeichen
PWD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{6,}$")

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def verify_pw(pw: str, ph: str) -> bool:
    return bool(ph) and hash_pw(pw) == ph

# ---------------------------------------------------------
# Schema-Sicherung (fügt fehlende Spalten hinzu)
# ---------------------------------------------------------
def _ensure_user_schema():
    with conn() as cn:
        c = cn.cursor()
        # users-Tabelle sicherstellen
        c.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                first_name TEXT,
                last_name TEXT,
                passhash TEXT,
                functions TEXT,
                units TEXT,
                role TEXT,             -- legacy (wird nicht mehr aktiv genutzt)
                scope TEXT,            -- legacy
                status TEXT NOT NULL DEFAULT 'active',   -- 'pending' | 'active' | 'disabled'
                created_at TEXT
            )
        """)
        # fehlende Spalten ggf. ergänzen
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        def _add(col, sql):
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {sql}")
        _add("status", "status TEXT NOT NULL DEFAULT 'active'")
        _add("functions", "functions TEXT")
        _add("units", "units TEXT")
        _add("created_at", "created_at TEXT")
        cn.commit()

def _role_from_functions(functions: str) -> str:
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    if "admin" in funcs or "betriebsleiter" in funcs:
        return "admin"
    return "user"

def seed_admin_if_empty():
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n == 0:
            c.execute("""
                INSERT INTO users(username, email, first_name, last_name, passhash, functions, status, created_at)
                VALUES(?,?,?,?,?,?,?,?)
            """, (
                "oklub",
                "admin@oklub.at",
                "OKlub",
                "Admin",
                hash_pw("OderKlub!"),
                "Admin",
                "active",
                datetime.utcnow().isoformat(),
            ))
            cn.commit()

def _fetch_user(username: str) -> Optional[Dict]:
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id, username, email, first_name, last_name, passhash, functions, units, status, created_at
            FROM users WHERE username=?
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
        "units": row[7] or "",
        "status": row[8] or "active",
        "created_at": row[9] or "",
    }

def _set_passhash(user_id: int, ph: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE users SET passhash=? WHERE id=?", (ph, user_id))
        cn.commit()

# ---------------------------------------------------------
# Registrierung
# ---------------------------------------------------------
def register_user(username: str, first_name: str, last_name: str, email: str, password: str) -> tuple[bool, str]:
    """
    Lege einen User mit status='pending' an. Admin muss freigeben.
    """
    _ensure_user_schema()

    if not username or not password or not email:
        return False, "Bitte alle Pflichtfelder ausfüllen."
    if not PWD_PATTERN.match(password):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."

    username = username.strip()
    with conn() as cn:
        c = cn.cursor()
        exists = c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            return False, "Benutzername ist bereits vergeben."
        c.execute("""
            INSERT INTO users(username, email, first_name, last_name, passhash, functions, status, created_at)
            VALUES(?,?,?,?,?,?,?,?)
        """, (
            username,
            email.strip(),
            first_name.strip(),
            last_name.strip(),
            hash_pw(password),
            "",              # noch keine Funktionen
            "pending",       # wartet auf Freigabe
            datetime.utcnow().isoformat(),
        ))
        cn.commit()
    return True, "Registrierung eingegangen. Wir prüfen deine Anfrage."

# ---------------------------------------------------------
# Login
# ---------------------------------------------------------
def _do_login(user: str, pw: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Rückgabe: (ok, role, functions). Login nur bei status='active'.
    """
    _ensure_user_schema()
    u = _fetch_user(user)
    if not u:
        return (False, None, None)

    # First login: falls passhash leer (nicht üblich bei Registrierung)
    if not u["passhash"]:
        if not pw:
            return (False, None, None)
        _set_passhash(u["id"], hash_pw(pw))
        u["passhash"] = hash_pw(pw)

    if not verify_pw(pw, u["passhash"]):
        return (False, None, None)

    if (u["status"] or "active") != "active":
        # Pending oder disabled -> kein Login
        return (False, None, None)

    role = _role_from_functions(u["functions"])

    st.session_state.auth       = True
    st.session_state.username   = u["username"]
    st.session_state.role       = role
    st.session_state.scope      = u["functions"]
    st.session_state.email      = u["email"]
    st.session_state.first_name = u["first_name"]
    st.session_state.last_name  = u["last_name"]
    st.session_state.login_ts   = datetime.utcnow().isoformat()

    return (True, role, u["functions"])

# ---------------------------------------------------------
# Admin-Helfer für Freigaben
# ---------------------------------------------------------
def list_pending_users() -> List[Dict]:
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT id, username, email, first_name, last_name, created_at
            FROM users WHERE status='pending' ORDER BY created_at ASC
        """).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "username": r[1],
            "email": r[2],
            "first_name": r[3] or "",
            "last_name": r[4] or "",
            "created_at": r[5] or "",
        })
    return out

def approve_user(username: str, functions: str) -> tuple[bool, str]:
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return False, "Benutzer nicht gefunden."
        c.execute("UPDATE users SET status='active', functions=? WHERE username=?", (functions.strip(), username))
        cn.commit()
    return True, "Benutzer freigegeben."

def reject_user(username: str) -> tuple[bool, str]:
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return False, "Benutzer nicht gefunden."
        # Entweder löschen oder auf 'disabled' setzen – hier löschen wir
        c.execute("DELETE FROM users WHERE username=?", (username,))
        cn.commit()
    return True, "Registrierung verworfen."

# ---------------------------------------------------------
# PW-Änderungen (bestehend)
# ---------------------------------------------------------
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
