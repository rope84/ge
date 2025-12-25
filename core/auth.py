"""# core/auth.py

Updated to use Argon2 for password hashing, support legacy SHA256 re-hashing on login,
remove hardcoded default admin password (seeded admin will be pending), and use logging.
"""

import re
import hashlib
import importlib
import logging
from datetime import datetime
from typing import Optional, Dict, Tuple, List
import os

import streamlit as st
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from core.db import conn

logger = logging.getLogger(__name__)
ph = PasswordHasher()

# -----------------------------
# Password Policy & Hashing
# -----------------------------
PWD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{6,}$")


def hash_pw(pw: str) -> str:
    """Hash password with Argon2. Empty strings return empty hash.
    """
    if not pw:
        return ""
    return ph.hash(pw)


def _verify_legacy_sha256(pw: str, phash: str) -> bool:
    """Verify legacy SHA256 hex hash."""
    if not phash:
        return False
    try:
        return hashlib.sha256(pw.encode("utf-8")).hexdigest() == (phash or "")
    except Exception:
        return False


def verify_pw(pw: str, phash: str) -> bool:
    """Verify password. Supports Argon2 hashes and legacy SHA256 hex hashes.
    Does not mutate DB here; migration is handled in login flow.
    """
    if not phash:
        return False

    # Argon2 hashes contain '$argon2' as part of the hash string
    if phash.startswith("$argon2"):
        try:
            return ph.verify(phash, pw)
        except (VerifyMismatchError, VerificationError):
            return False
        except Exception as e:
            logger.exception("Argon2 verification error: %s", e)
            return False

    # Fallback: legacy SHA256 hex digest
    return _verify_legacy_sha256(pw, phash)


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


def _set_passhash(user_id: int, phash: str) -> None:
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE users SET passhash=? WHERE id= ?", (phash, user_id))
        cn.commit()


# -----------------------------
# Admin seeding & consistency
# -----------------------------
def seed_admin_if_empty():
    """If no users exist, create a default 'oklub' user in PENDING state (no password).
    This avoids having a predictable default admin password.
    """
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
                # create pending admin (no password). Admin must be activated via normal flow.
                c.execute("""
                    INSERT INTO users(username, email, first_name, last_name,
                                      passhash, functions, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
                """, (
                    "oklub", "admin@oklub.at", "OKlub", "Admin",
                    "", "Admin"
                ))
                cn.commit()
                logger.info("Default admin 'oklub' created in PENDING state. Set password and activate via admin flow.")
    except Exception as e:
        logger.exception("Error in seed_admin_if_empty(): %s", e)


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
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
                """, (
                    "oklub", "admin@oklub.at", "OKlub", "Admin",
                    "", "Admin"
                ))
            else:
                uid, phash = row
                # ensure functions set but keep status as pending if there is no password
                c.execute("UPDATE users SET functions='Admin' WHERE id=?", (uid,))
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

    phash = u.get("passhash") or ""

    # If legacy SHA256 stored, verify and re-hash with Argon2 on success
    if phash and not phash.startswith("$argon2"):
        if _verify_legacy_sha256(pw, phash):
            try:
                new_hash = hash_pw(pw)
                _set_passhash(u["id"], new_hash)
                phash = new_hash
                logger.info("Upgraded legacy password hash to Argon2 for user %s", uname)
            except Exception:
                logger.exception("Failed to migrate legacy hash for user %s", uname)
                return False, None, None
        else:
            return False, None, None

    if not verify_pw(pw, phash):
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
        if c.execute("SELECT 1 FROM users WHERE username= ?", (username.strip(),)).fetchone():
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


# End of file
