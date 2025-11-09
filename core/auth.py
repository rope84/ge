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
# Schema-Sicherung
# -----------------------------
# core/auth.py – im Block _ensure_user_schema()

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
                created_at TEXT
            )
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}

        def _add(col: str, ddl: str):
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {ddl}")

        _add("passhash",   "passhash   TEXT NOT NULL DEFAULT ''")
        _add("functions",  "functions  TEXT DEFAULT ''")
        _add("status",     "status     TEXT NOT NULL DEFAULT 'active'")
        _add("created_at", "created_at TEXT")
        # ⬇️ NEU: Units-Spalte für Zuweisungen (z. B. "bar:1,bar:2,cash:1")
        _add("units",      "units      TEXT DEFAULT ''")

        c.execute("UPDATE users SET passhash   = COALESCE(passhash,'')")
        c.execute("UPDATE users SET functions  = COALESCE(functions,'')")
        c.execute("UPDATE users SET status     = COALESCE(status,'active')")
        c.execute("UPDATE users SET created_at = COALESCE(created_at, datetime('now'))")
        c.execute("UPDATE users SET units      = COALESCE(units,'')")  # ⬅️ Backfill
        cn.commit()

# -----------------------------
# Role resolution (functions → role)
# -----------------------------
def _role_from_functions(functions: str) -> str:
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    if "admin" in funcs or "betriebsleiter" in funcs:
        return "admin"
    return "user"

def is_admin_session() -> bool:
    """Bequemer Helper für UI (Tabs, Badges …)."""
    return (st.session_state.get("role") or "").lower() == "admin"

# -----------------------------
# User fetch / helpers
# -----------------------------
# modules/start.py – robuste Variante
def _fetch_user(username: str) -> Optional[tuple]:
    with conn() as cn:
        c = cn.cursor()
        # Prüfen, ob 'units' existiert
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        if "units" in cols:
            return c.execute(
                "SELECT id, username, functions, units FROM users WHERE username=?",
                (username,),
            ).fetchone()
        else:
            # Fallback ohne units – liefere leeren String an Position 3
            row = c.execute(
                "SELECT id, username, functions FROM users WHERE username=?",
                (username,),
            ).fetchone()
            if not row:
                return None
            return (row[0], row[1], row[2], "")

def _set_passhash(user_id: int, ph: str) -> None:
    with conn() as cn:
        c = cn.cursor()
        c.execute("UPDATE users SET passhash=? WHERE id=?", (ph, user_id))
        cn.commit()

# -----------------------------
# Seed & Consistency
# -----------------------------
def seed_admin_if_empty() -> None:
    """Falls noch kein User existiert, einen Default-Admin anlegen."""
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n == 0:
            c.execute("""
                INSERT INTO users(username, email, first_name, last_name, passhash, functions, status, created_at)
                VALUES(?,?,?,?,?,?,?, datetime('now'))
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
    - Schema sicherstellen
    - mindestens einen aktiven Admin/Betriebsleiter garantieren
    - 'oklub' seeden/auffrischen falls nötig
    """
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        have_admin = c.execute("""
            SELECT 1
              FROM users
             WHERE LOWER(COALESCE(status,'active'))='active'
               AND (lower(functions) LIKE '%admin%' OR lower(functions) LIKE '%betriebsleiter%')
             LIMIT 1
        """).fetchone()
        if not have_admin:
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
                c.execute("UPDATE users SET functions='Admin', status='active' WHERE id=?", (uid,))
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
    _ensure_user_schema()
    u = _fetch_user(user)
    if not u:
        return (False, None, None)

    # Status prüfen
    if (u["status"] or "active").lower() != "active":
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
    _ensure_user_schema()

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
            VALUES(?,?,?,?,?,?,?, datetime('now'))
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
    _ensure_user_schema()
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

def pending_count() -> int:
    """Anzahl offener Registrierungen (für Badge/Übersicht)."""
    _ensure_user_schema()
    with conn() as cn:
        c = cn.cursor()
        n = c.execute("""
            SELECT COUNT(*) FROM users
             WHERE LOWER(COALESCE(status,'active'))='pending'
        """).fetchone()[0]
    return int(n or 0)

def approve_user(username: str, functions: str) -> Tuple[bool, str]:
    _ensure_user_schema()
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
    _ensure_user_schema()
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
    _ensure_user_schema()
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
