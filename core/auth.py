# auth.py
import re
import hashlib
import streamlit as st
from core.db import conn
from datetime import datetime
from core.config import APP_NAME, APP_VERSION

# sehr simple Policy: min 6, 1 Großbuchstabe, 1 Sonderzeichen
PWD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{6,}$")

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def verify_pw(pw: str, ph: str) -> bool:
    return hash_pw(pw) == ph

def seed_admin_if_empty():
    with conn() as cn:
        c = cn.cursor()
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n == 0:
            c.execute("""
                INSERT INTO users(username,passhash,role,scope,email,first_name,last_name)
                VALUES(?,?,?,?,?,?,?)
            """, ("oklub", hash_pw("OderKlub!"), "admin", "", "admin@oklub.at", "OKlub", "Admin"))
            cn.commit()

def _do_login(user, pw) -> bool:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id, username, passhash, role, scope, email, first_name, last_name
            FROM users WHERE username=?
        """, (user.strip(),)).fetchone()
    if not row:
        return False
    uid, uname, ph, role, scope, email, fn, ln = row
    if not verify_pw(pw, ph):
        return False
    st.session_state.auth = True
    st.session_state.username   = uname
    st.session_state.role       = role
    st.session_state.scope      = scope or ""
    st.session_state.email      = email or ""
    st.session_state.first_name = fn or ""
    st.session_state.last_name  = ln or ""
    st.session_state.login_ts   = datetime.utcnow().iso_format() if hasattr(datetime, "iso_format") else datetime.utcnow().isoformat()
    return True

def login_required(app_name: str, app_version: str):
    st.markdown(f"<div style='height:8px'></div>", unsafe_allow_html=True)

    st.caption(app_version)
    st.subheader("Login")

    u = st.text_input("Benutzername")
    p = st.text_input("Passwort", type="password")

    c1, c2 = st.columns([2,1])
    if c1.button("Anmelden", use_container_width=True):
        if not _do_login(u, p):
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
        if not verify_pw(old_pw, row[0]):
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
