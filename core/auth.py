import re
import hashlib
import importlib
from datetime import datetime
from typing import Optional, Dict, Tuple, List

import streamlit as st

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
# Schema-Sicherung
# -----------------------------
def _ensure_user_schema() -> None:
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT NOT NULL UNIQUE,
                email      TEXT,
                first_name TEXT,
                last_name  TEXT,
                passhash   TEXT NOT NULL DEFAULT '',
                functions  TEXT DEFAULT '',
                status     TEXT NOT NULL DEFAULT 'active',
                created_at TEXT,
                units      TEXT DEFAULT ''
            )
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}

        def _add(col: str, ddl: str):
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {ddl}")

        _add("passhash", "passhash   TEXT NOT NULL DEFAULT ''")
        _add("functions", "functions  TEXT DEFAULT ''")
        _add("status", "status     TEXT NOT NULL DEFAULT 'active'")
        _add("created_at", "created_at TEXT")
        _add("units", "units      TEXT DEFAULT ''")

        c.execute("UPDATE users SET passhash   = COALESCE(passhash, '')")
        c.execute("UPDATE users SET functions  = COALESCE(functions, '')")
        c.execute("UPDATE users SET status     = COALESCE(status, 'active')")
        c.execute("UPDATE users SET created_at = COALESCE(created_at, datetime('now'))")
        c.execute("UPDATE users SET units      = COALESCE(units, '')")
        cn.commit()


# -----------------------------
# Role resolution
# -----------------------------
def _role_from_functions(functions: str) -> str:
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    if "admin" in funcs or "betriebsleiter" in funcs:
        return "admin"
    return "user"


def is_admin_session() -> bool:
    return (st.session_state.get("role") or "").lower() == "admin"


# -----------------------------
# User fetch / helpers
# -----------------------------
def _fetch_user(username: str) -> Optional[Dict]:
    uname = (username or "").strip()
    if not uname:
        return None
    try:
        with conn() as cn:
            c = cn.cursor()
            row = c.execute("""
                SELECT id, username, email, first_name, last_name,
                       passhash, functions, status, created_at, units
                  FROM users
                 WHERE username=?
            """, (uname,)).fetchone()
    except Exception:
        return None
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
        "units": row[9] or "",
    }


def _set_passhash(user_id: int, ph: str) -> None:
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE users SET passhash=? WHERE id=?", (ph, user_id))
        cn.commit()


# -----------------------------
# Admin seeding & consistency
# -----------------------------
def seed_admin_if_empty():
    try:
        with conn() as cn:
            c = cn.cursor()
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
                    created_at TEXT,
                    units      TEXT DEFAULT ''
                )
            """)
            cn.commit()
            if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
                c.execute("""
                    INSERT INTO users(username, email, first_name, last_name,
                                      passhash, functions, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', datetime('now'))
                """, (
                    "oklub", "admin@oklub.at", "OKlub", "Admin",
                    hash_pw("OderKlub!"), "Admin"
                ))
                cn.commit()
                print("✅ Default-Admin 'oklub' wurde angelegt (Passwort: OderKlub!)")
    except Exception as e:
        print(f"⚠️ Fehler in seed_admin_if_empty(): {e}")


def ensure_admin_consistency() -> None:
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        admin_exists = c.execute("""
            SELECT 1 FROM users
             WHERE LOWER(COALESCE(status,'active'))='active'
               AND (LOWER(functions) LIKE '%admin%' OR LOWER(functions) LIKE '%betriebsleiter%')
             LIMIT 1
        """).fetchone()

        if not admin_exists:
            row = c.execute("SELECT id, passhash FROM users WHERE username=?", ("oklub",)).fetchone()
            if row is None:
                c.execute("""
                    INSERT INTO users(username, email, first_name, last_name,
                                      passhash, functions, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', datetime('now'))
                """, (
                    "oklub", "admin@oklub.at", "OKlub", "Admin",
                    hash_pw("OderKlub!"), "Admin"
                ))
            else:
                uid, ph = row
                c.execute("UPDATE users SET functions='Admin', status='active' WHERE id=?", (uid,))
                if not ph:
                    c.execute("UPDATE users SET passhash=? WHERE id=?", (hash_pw("OderKlub!"), uid))
        cn.commit()


# -----------------------------
# Login / Session init
# -----------------------------
def _do_login(user: str, pw: str) -> Tuple[bool, Optional[str], Optional[str]]:
    uname = (user or "").strip()
    if not uname or not pw:
        return False, None, None

    u = _fetch_user(uname)
    if not u or u.get("status") != "active":
        return False, None, None

    ph = u.get("passhash") or ""
    if not ph:
        ph = hash_pw(pw)
        try:
            _set_passhash(u["id"], ph)
        except Exception:
            return False, None, None

    if not verify_pw(pw, ph):
        return False, None, None

    role = _role_from_functions(u.get("functions") or "")
    st.session_state.update({
        "auth": True,
        "username": u["username"],
        "role": role,
        "scope": u.get("functions", ""),
        "email": u.get("email", ""),
        "first_name": u.get("first_name", ""),
        "last_name": u.get("last_name", ""),
        "login_ts": datetime.utcnow().isoformat(),
    })
    return True, role, u.get("functions", "")


# -----------------------------
# Registration
# -----------------------------
def register_user(username: str, first_name: str, last_name: str, email: str, password: str) -> Tuple[bool, str]:
    _ensure_user_schema()
    if not all([username, email, first_name, last_name, password]):
        return False, "Bitte alle Felder ausfüllen."
    if not PWD_PATTERN.match(password):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."

    with conn() as cn:
        c = cn.cursor()
        if c.execute("SELECT 1 FROM users WHERE username=?", (username.strip(),)).fetchone():
            return False, "Benutzername ist bereits vergeben."
        c.execute("""
            INSERT INTO users(username, email, first_name, last_name,
                              passhash, functions, status, created_at)
            VALUES (?, ?, ?, ?, ?, '', 'pending', datetime('now'))
        """, (
            username.strip(), email.strip(), first_name.strip(),
            last_name.strip(), hash_pw(password)
        ))
        cn.commit()
    return True, "Registrierung eingegangen. Wir prüfen deine Anfrage."


# -----------------------------
# Admin Actions
# -----------------------------
def list_pending_users() -> List[Dict]:
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT username, email, first_name, last_name, created_at
              FROM users
             WHERE LOWER(COALESCE(status,'active'))='pending'
             ORDER BY datetime(COALESCE(created_at, '1970-01-01')) DESC
        """).fetchall()
    return [{
        "username": r[0],
        "email": r[1] or "",
        "first_name": r[2] or "",
        "last_name": r[3] or "",
        "created_at": r[4] or ""
    } for r in rows]


def pending_count() -> int:
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        return c.execute("""
            SELECT COUNT(*) FROM users WHERE LOWER(COALESCE(status,'active'))='pending'
        """).fetchone()[0] or 0


def approve_user(username: str, functions: str) -> Tuple[bool, str]:
    _ensure_user_schema()
    if not username:
        return False, "Kein Benutzername übergeben."
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id FROM users
             WHERE username=? AND LOWER(COALESCE(status,'active'))='pending'
        """, (username,)).fetchone()
        if not row:
            return False, "Benutzer nicht (mehr) pending."
        c.execute("""
            UPDATE users SET status='active', functions=? WHERE username=?
        """, (functions.strip(), username))
        cn.commit()
    return True, f"Benutzer '{username}' freigegeben."


def reject_user(username: str) -> Tuple[bool, str]:
    _ensure_user_schema()
    if not username:
        return False, "Kein Benutzername übergeben."
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id FROM users
             WHERE username=? AND LOWER(COALESCE(status,'active'))='pending'
        """, (username,)).fetchone()
        if not row:
            return False, "Benutzer nicht (mehr) pending."
        c.execute("DELETE FROM users WHERE username=?", (username,))
        cn.commit()
    return True, f"Registrierung '{username}' verworfen und gelöscht."


# -----------------------------
# Password Management
# -----------------------------
def change_password(username: str, old_pw: str, new_pw: str) -> Tuple[bool, str]:
    _ensure_user_schema()
    if not PWD_PATTERN.match(new_pw):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT passhash FROM users
             WHERE username=? AND LOWER(COALESCE(status,'active'))='active'
        """, (username,)).fetchone()
        if not row or not verify_pw(old_pw, row[0] or ""):
            return False, "Altes Passwort stimmt nicht."
        c.execute("UPDATE users SET passhash=? WHERE username=?", (hash_pw(new_pw), username))
        cn.commit()
    return True, "Passwort aktualisiert."


def admin_set_password(username: str, new_pw: str) -> Tuple[bool, str]:
    _ensure_user_schema()
    if not PWD_PATTERN.match(new_pw):
        return False, "Passwort zu schwach (min. 6, 1 Großbuchstabe, 1 Sonderzeichen)."
    with conn() as cn:
        c = cn.cursor()
        if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return False, "Benutzer nicht gefunden."
        c.execute("UPDATE users SET passhash=? WHERE username=?", (hash_pw(new_pw), username))
        cn.commit()
    return True, "Passwort gesetzt."
