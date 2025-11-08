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
    # konsistent: sha256 HEX
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

def seed_admin_if_empty():
    with conn() as cn:
        c = cn.cursor()
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n == 0:
            c.execute("""
                INSERT INTO users(username, email, first_name, last_name, passhash, functions, created_at)
                VALUES(?,?,?,?,?,?,datetime('now'))
            """, (
                "oklub",
                "admin@oklub.at",
                "OKlub",
                "Admin",
                hash_pw("OderKlub!"),
                "Admin",  # wichtig: functions legt Rolle fest
            ))
            cn.commit()

def _fetch_user(username: str) -> Optional[Dict]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id, username, email, first_name, last_name, passhash, functions, created_at
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
        "created_at": row[7] or "",
    }

def _set_passhash(user_id: int, ph: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE users SET passhash=? WHERE id=?", (ph, user_id))
        cn.commit()

def _do_login(user: str, pw: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Rückgabe: (ok, role, functions)
      - ok: True/False
      - role: 'admin' | 'user' (nur wenn ok=True)
      - functions: originaler Functions-String (nur wenn ok=True)
    """
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

    role = _role_from_functions(u["functions"])

    # Session-State füllen
    st.session_state.auth = True
    st.session_state.username   = u["username"]
    st.session_state.role       = role
    st.session_state.scope      = u["functions"]    # hier speichern wir den Functions-String
    st.session_state.email      = u["email"]
    st.session_state.first_name = u["first_name"]
    st.session_state.last_name  = u["last_name"]
    st.session_state.login_ts   = datetime.utcnow().isoformat()

    return (True, role, u["functions"])

def login_required(app_name: str, app_version: str):
    # Minimal-Login-UI (falls du es irgendwo standalone nutzt)
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
    """Von Nutzer aufgerufen (Profil)."""
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
    """Admin setzt fremdes Passwort."""
    if not PWD_PATTERN.match(new_pw):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."
    with conn() as cn:
        c = cn.cursor()
        if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return False, "Benutzer nicht gefunden."
        c.execute("UPDATE users SET passhash=? WHERE username=?", (hash_pw(new_pw), username))
        cn.commit()
    return True, "Passwort gesetzt."
