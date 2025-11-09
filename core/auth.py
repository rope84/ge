# core/auth.py
import re
import hashlib
import streamlit as st
from datetime import datetime
from typing import Optional, Dict, Tuple, List
from core.db import conn

# -----------------------------
# Password Policy & Hashing
# -----------------------------
PWD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{6,}$")

def hash_pw(pw: str) -> str:
    return hashlib.sha256((pw or "").encode("utf-8")).hexdigest()

def verify_pw(pw: str, ph: str) -> bool:
    if not ph:
        return False
    return hash_pw(pw) == (ph or "")

# -----------------------------
# Role resolution (functions → role)
# -----------------------------
def _role_from_functions(functions: str) -> str:
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    if "admin" in funcs or "betriebsleiter" in funcs:
        return "admin"
    return "user"

# -----------------------------
# User fetch / helpers
# -----------------------------
def _fetch_user(username: str) -> Optional[Dict]:
    if not username:
        return None
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id, username, email, first_name, last_name, passhash, functions, status, created_at
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
        "status": (row[7] or "active").lower(),
        "created_at": row[8] or "",
    }

def _set_passhash(user_id: int, ph: str) -> None:
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE users SET passhash=? WHERE id=?", (ph, user_id))
        cn.commit()

# -----------------------------
# Seed & consistency
# -----------------------------
def seed_admin_if_empty():
    """
    Falls es noch keinen User gibt, einen Default-Admin anlegen.
    """
    with conn() as cn:
        c = cn.cursor()
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n == 0:
            c.execute("""
                INSERT INTO users(username, email, first_name, last_name, passhash, functions, status, created_at)
                VALUES(?,?,?,?,?,?,?,datetime('now'))
            """, (
                "oklub",
                "admin@oklub.at",
                "OKlub",
                "Admin",
                hash_pw("OderKlub!"),
                "Admin",
                "active",
            ))
            cn.commit()

def ensure_admin_consistency() -> None:
    """
    Stellt sicher, dass:
      - Tabelle users existiert (Schema minimal),
      - Spalten 'functions' und 'status' vorhanden sind,
      - mind. ein Admin existiert (Seed 'oklub' falls nötig).
    Läuft idempotent und darf beliebig oft aufgerufen werden.
    """
    from core.db import conn  # local import, um Zyklen zu vermeiden

    with conn() as cn:
        c = cn.cursor()

        # 1) Tabelle users sicherstellen (minimal – vorhandene Felder bleiben erhalten)
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT NOT NULL UNIQUE,
                email      TEXT,
                first_name TEXT,
                last_name  TEXT,
                passhash   TEXT NOT NULL DEFAULT '',
                functions  TEXT DEFAULT '',
                status     TEXT DEFAULT 'active',
                created_at TEXT
            )
        """)

        # 2) Fehlende Spalten dynamisch ergänzen
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        if "functions" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN functions TEXT DEFAULT ''")
        if "passhash" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN passhash TEXT NOT NULL DEFAULT ''")
        if "status" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'")
        if "created_at" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN created_at TEXT")

        # 3) Null-Werte glätten
        c.execute("UPDATE users SET passhash = COALESCE(passhash,'')")
        c.execute("UPDATE users SET functions = COALESCE(functions,'')")
        c.execute("UPDATE users SET status    = COALESCE(status,'active')")
        c.execute("UPDATE users SET created_at= COALESCE(created_at, datetime('now'))")

        # 4) Existiert ein Admin? (Admin ODER Betriebsleiter zählt)
        have_admin = c.execute("""
            SELECT 1
              FROM users
             WHERE status='active'
               AND (
                    lower(functions) LIKE '%admin%'
                 OR lower(functions) LIKE '%betriebsleiter%'
               )
             LIMIT 1
        """).fetchone()

        if not have_admin:
            # fallback-seed "oklub" als Admin – falls nicht vorhanden
            row = c.execute("SELECT id, passhash FROM users WHERE username=?", ("oklub",)).fetchone()
            if row is None:
                c.execute("""
                    INSERT INTO users(username, email, first_name, last_name, passhash, functions, status, created_at)
                    VALUES(?,?,?,?,?,?, 'active', datetime('now'))
                """, (
                    "oklub",
                    "admin@oklub.at",
                    "OKlub",
                    "Admin",
                    hash_pw("OderKlub!"),
                    "Admin",
                ))
            else:
                uid, ph = row
                # Rolle admin sicherstellen
                c.execute("UPDATE users SET functions=? WHERE id=?", ("Admin", uid))
                # Falls leer, default Passwort setzen (nur wenn wirklich leer)
                if not ph:
                    c.execute("UPDATE users SET passhash=? WHERE id=?", (hash_pw("OderKlub!"), uid))

        cn.commit()

# -----------------------------
# Login
# -----------------------------
def _do_login(user: str, pw: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Returns: (ok, role, functions)
    - ok: True/False
    - role: 'admin'|'user' (nur wenn ok=True)
    - functions: originaler Functions-String (nur wenn ok=True)
    """
    u = _fetch_user(user)
    if not u:
        return (False, None, None)

    # Status prüfen
    status = (u["status"] or "active").lower()
    if status != "active":
        # Pending / disabled -> kein Login
        return (False, None, None)

    # First Login: wenn kein passhash gesetzt, jetzt setzen (nur wenn pw geliefert)
    if not u["passhash"]:
        if not pw:
            return (False, None, None)
        _set_passhash(u["id"], hash_pw(pw))
        u["passhash"] = hash_pw(pw)

    if not verify_pw(pw, u["passhash"]):
        return (False, None, None)

    role = _role_from_functions(u["functions"])

    # Session setzen
    st.session_state.auth = True
    st.session_state.username   = u["username"]
    st.session_state.role       = role
    st.session_state.scope      = u["functions"] or ""
    st.session_state.email      = u["email"]
    st.session_state.first_name = u["first_name"]
    st.session_state.last_name  = u["last_name"]
    st.session_state.login_ts   = datetime.utcnow().isoformat()

    return (True, role, u["functions"])

# -----------------------------
# Registration (public)
# -----------------------------
def register_user(username: str, first_name: str, last_name: str, email: str, password: str) -> Tuple[bool, str]:
    """
    Legt einen Benutzer mit status='pending' an.
    Passwort wird bereits gehasht gespeichert; Login ist bis Freigabe blockiert.
    """
    if not username or not email or not first_name or not last_name or not password:
        return False, "Bitte alle Felder ausfüllen."
    if not PWD_PATTERN.match(password):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."

    with conn() as cn:
        c = cn.cursor()
        exists = c.execute("SELECT 1 FROM users WHERE username=?", (username.strip(),)).fetchone()
        if exists:
            return False, "Benutzername ist bereits vergeben."
        c.execute("""
            INSERT INTO users(username, email, first_name, last_name, passhash, functions, status, created_at)
            VALUES(?,?,?,?,?,?,?,datetime('now'))
        """, (
            username.strip(),
            email.strip(),
            first_name.strip(),
            last_name.strip(),
            hash_pw(password),
            "",              # noch keine Funktionen
            "pending",       # muss Admin freigeben
        ))
        cn.commit()
    return True, "Registrierung eingegangen. Wir prüfen deine Anfrage."

# -----------------------------
# Admin: pending queue
# -----------------------------
def list_pending_users() -> List[Dict]:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT username, email, first_name, last_name, created_at
              FROM users
             WHERE LOWER(COALESCE(status,'active'))='pending'
             ORDER BY datetime(COALESCE(created_at, '1970-01-01')) DESC
        """).fetchall()
    out: List[Dict] = []
    for r in rows:
        out.append({
            "username": r[0],
            "email": r[1] or "",
            "first_name": r[2] or "",
            "last_name": r[3] or "",
            "created_at": r[4] or "",
        })
    return out

def approve_user(username: str, functions: str) -> Tuple[bool, str]:
    if not username:
        return False, "Kein Benutzername übergeben."
    fn = (functions or "").strip()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT id FROM users WHERE username=? AND LOWER(COALESCE(status,'active'))='pending'", (username,)).fetchone()
        if not row:
            return False, "Benutzer nicht (mehr) pending."
        c.execute("""
            UPDATE users
               SET status='active',
                   functions=?
             WHERE username=?
        """, (fn, username))
        cn.commit()
    return True, f"Benutzer '{username}' freigegeben."

def reject_user(username: str) -> Tuple[bool, str]:
    if not username:
        return False, "Kein Benutzername übergeben."
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT id FROM users WHERE username=? AND LOWER(COALESCE(status,'active'))='pending'", (username,)).fetchone()
        if not row:
            return False, "Benutzer nicht (mehr) pending."
        c.execute("DELETE FROM users WHERE username=?", (username,))
        cn.commit()
    return True, f"Registrierung '{username}' verworfen und gelöscht."

# -----------------------------
# Password management
# -----------------------------
def change_password(username: str, old_pw: str, new_pw: str) -> tuple[bool, str]:
    """Von Nutzer aufgerufen (Profil)."""
    if not PWD_PATTERN.match(new_pw):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT passhash FROM users WHERE username=? AND LOWER(COALESCE(status,'active'))='active'", (username,)).fetchone()
        if not row:
            return False, "Benutzer nicht gefunden oder nicht aktiv."
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
