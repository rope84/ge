import streamlit as st
import pandas as pd
import shutil
import time
import datetime
from pathlib import Path
from typing import Optional, List, Dict

from core.db import BACKUP_DIR, DB_PATH, conn
from core.ui_theme import page_header, section_title
from core.auth import change_password
from core.config import APP_NAME, APP_VERSION


# ---------------- Änderungsnotizen (Default) ----------------
DEFAULT_CHANGELOG_NOTES = {
    "Beta 1": [
        "Neues einheitliches UI-Theme & aufgeräumte Navigation",
        "Admin-Cockpit mit Startseite & KPIs",
        "Verbessertes Profil-Modul inkl. Passwort ändern",
        "Inventur mit Monatslogik & PDF-Export",
        "Abrechnung poliert: Garderobe-Logik, Voucher-Einbezug",
        "Datenbank-Backups: manuell, Statusanzeige"
    ]
}


# ---------------- Hilfsfunktionen / DB ----------------
def _table_exists(c, name: str) -> bool:
    return c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None


def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()

        tables_sql = {
            "users": """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    email TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    passhash TEXT NOT NULL DEFAULT ''
                )
            """,
            "employees": """
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    contract TEXT NOT NULL,
                    hourly REAL NOT NULL DEFAULT 0,
                    is_barlead INTEGER NOT NULL DEFAULT 0,
                    bar_no INTEGER
                )
            """,
            "fixcosts": """
                CREATE TABLE IF NOT EXISTS fixcosts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL DEFAULT 0,
                    note TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
            """,
            "meta": """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """,
            "changelog": """
                CREATE TABLE IF NOT EXISTS changelog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    version TEXT NOT NULL,
                    note TEXT NOT NULL
                )
            """
        }

        for name, sql in tables_sql.items():
            if not _table_exists(c, name):
                c.execute(sql)
        cn.commit()


def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None


def _set_meta(key: str, value: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (key, value))
        cn.commit()


def _get_meta_many(keys: List[str]) -> Dict[str, Optional[str]]:
    with conn() as cn:
        c = cn.cursor()
        return {
            k: (r[0] if (r := c.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()) else None)
            for k in keys
        }


def _set_meta_many(data: Dict[str, str]):
    with conn() as cn:
        c = cn.cursor()
        for k, v in data.items():
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (k, v))
        cn.commit()


def _insert_changelog(version: str, notes: List[str]):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        rows = [(now, version, note) for note in notes]
        c.executemany("INSERT INTO changelog(created_at, version, note) VALUES(?,?,?)", rows)
        cn.commit()


def _ensure_version_logged():
    last = _get_meta("last_seen_version")
    if last != APP_VERSION:
        notes = DEFAULT_CHANGELOG_NOTES.get(APP_VERSION, [f"Update auf {APP_VERSION}"])
        _insert_changelog(APP_VERSION, notes)
        _set_meta("last_seen_version", APP_VERSION)


def _count_rows(table: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, table):
            return 0
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------- Backups (manuell, BCK_YYYYMMDD_HHMMSS.bak) ----------------
def _list_backups() -> List[Path]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(BACKUP_DIR.glob("BCK_*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)


def _last_backup_time() -> Optional[datetime.datetime]:
    files = _list_backups()
    return datetime.datetime.fromtimestamp(max(files, key=lambda f: f.stat().st_mtime).stat().st_mtime) if files else None


def _create_backup() -> Optional[Path]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"BCK_{ts}.bak"
    shutil.copy(DB_PATH, target)
    return target


def _restore_backup(file_path: Path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(DB_PATH, BACKUP_DIR / f"pre_restore_{int(time.time())}.bak")
    shutil.copy(file_path, DB_PATH)


def _format_size(bytes_: int) -> str:
    return f"{bytes_ / (1024 * 1024):.1f} MB"


def _db_size_mb() -> float:
    try:
        return round(DB_PATH.stat().st_size / (1024 * 1024), 2)
    except Exception:
        return 0.0


# ---------------- UI Helpers ----------------
def _status_badge_from_days(days: Optional[int]) -> tuple[str, str, str]:
    if days is None:
        return ("#ef4444", "Kein Backup", "Es wurde noch kein Backup gefunden.")
    if days <= 5:
        return ("#22c55e", "Aktuell", f"Letztes Backup ist {days} Tag(e) alt.")
    if days <= 7:
        return ("#f59e0b", "Bald fällig", f"Letztes Backup ist {days} Tag(e) alt (empfohlen: ≤5 Tage).")
    return ("#ef4444", "Überfällig", f"Letztes Backup ist {days} Tag(e) alt (kritisch).")


def _small_status_card(title: str, color: str, lines: List[str]) -> str:
    body = "<br/>".join([f"<span style='opacity:0.85;font-size:12px;'>{ln}</span>" for ln in lines])
    return f"""
    <div style="display:flex; gap:10px; align-items:flex-start;
        background:rgba(255,255,255,0.03); padding:10px 12px; border-radius:10px;">
      <span style='display:inline-block; width:10px; height:10px; border-radius:50%; margin-top:4px; background:{color};'></span>
      <div style='font-size:13px;'><b>{title}</b><br/>{body}</div>
    </div>
    """


# ---------------- Übersicht ----------------
def _render_home():
    # Live-Zahlen
    users_cnt = _count_rows("users")
    emp_cnt = _count_rows("employees")
    fix_cnt = _count_rows("fixcosts")
    backups = _list_backups()
    total_backups = len(backups)

    last_bkp_dt = _last_backup_time()
    days_since = None if last_bkp_dt is None else (datetime.date.today() - last_bkp_dt.date()).days
    color, label, tip = _status_badge_from_days(days_since)

    db_size = _db_size_mb()

    # Systemhinweise
    issues = []
    if users_cnt == 0:
        issues.append("Keine Benutzer angelegt.")
    if emp_cnt == 0:
        issues.append("Keine Mitarbeiter angelegt.")
    if color in ("#f59e0b", "#ef4444"):
        issues.append(tip)

    left, right = st.columns(2, gap="large")

    with left:
        today_str = datetime.date.today().strftime("%d.%m.%Y")
        html = _small_status_card(
            "Systemstatus",
            "#22c55e" if not issues else "#f59e0b" if any("empfohlen" in x for x in issues) else "#ef4444",
            [
                f"Prüfung: {today_str}",
                f"Benutzer: {users_cnt}",
                f"Mitarbeiter: {emp_cnt}",
                f"Fixkosten: {fix_cnt}"
            ]
        )
        st.markdown(html, unsafe_allow_html=True)

    with right:
        last_text = "—" if not last_bkp_dt else last_bkp_dt.strftime("%d.%m.%Y %H:%M")
        html_b = _small_status_card(
            "Backupstatus",
            color,
            [
                f"Status: {label}",
                f"Info: {tip}",
                f"Letztes Backup: {last_text}",
                f"Backups gesamt: {total_backups}"
            ]
        )
        st.markdown(html_b, unsafe_allow_html=True)

    # Details nur bei Warnungen/Fehlern sichtbar
    if issues:
        with st.expander("🔍 Systemhinweise öffnen", expanded=False):
            for issue in issues:
                st.markdown(f"- {issue}")
    else:
        st.caption("🟢 Keine Systemhinweise")

    st.divider()

    # --- Datenbank Block ---
    section_title("🗂️ Datenbankstatus")
    db_details = [
        f"📦 Dateigröße: **{db_size} MB**",
        f"🧩 Tabellen vorhanden: **{_count_rows('meta') + _count_rows('users') + _count_rows('employees') + _count_rows('fixcosts')} (inkl. Systemtabellen)**",
        f"💾 Gesamtanzahl Backups: **{total_backups}**"
    ]
    for d in db_details:
        st.markdown(d)

    st.divider()

    # --- Changelog ---
    section_title("📝 Änderungsprotokoll")
    with conn() as cn:
        df = pd.read_sql("SELECT created_at, version, note FROM changelog ORDER BY datetime(created_at) DESC LIMIT 20", cn)
    if df.empty:
        st.info("Keine Einträge im Changelog.")
    else:
        for _, r in df.iterrows():
            st.markdown(
                f"<div style='font-size:12px;opacity:0.8;'><b>{r['version']}</b> – {r['created_at'][:16]}: {r['note']}</div>",
                unsafe_allow_html=True
            )


# ---------------- Betrieb (Grundparameter) ----------------
def _render_business_admin():
    section_title("🏢 Grundparameter des Betriebs")

    keys = [
        "business_name",
        "business_street",
        "business_zip",
        "business_city",
        "business_phone",
        "business_email",
        "business_uid",
        "business_iban",
        "business_note",
    ]
    values = _get_meta_many(keys)

    with st.form("business_form"):
        a, b = st.columns([2, 2])
        name = a.text_input("Name des Betriebs", value=values.get("business_name") or "")
        phone = b.text_input("Telefon", value=values.get("business_phone") or "")
        c, d = st.columns([3, 1])
        street = c.text_input("Straße & Hausnummer", value=values.get("business_street") or "")
        zip_code = d.text_input("PLZ", value=values.get("business_zip") or "")
        city = st.text_input("Ort / Stadt", value=values.get("business_city") or "")
        e, f = st.columns(2)
        email = e.text_input("E-Mail", value=values.get("business_email") or "")
        uid = f.text_input("UID", value=values.get("business_uid") or "")
        g, h = st.columns(2)
        iban = g.text_input("IBAN", value=values.get("business_iban") or "")
        note = h.text_input("Notiz (optional)", value=values.get("business_note") or "")

        if st.form_submit_button("💾 Speichern", use_container_width=True):
            _set_meta_many({
                "business_name": name,
                "business_street": street,
                "business_zip": zip_code,
                "business_city": city,
                "business_phone": phone,
                "business_email": email,
                "business_uid": uid,
                "business_iban": iban,
                "business_note": note,
            })
            st.success("Betriebsdaten gespeichert.")


# ---------------- Haupt-Render ----------------
def render_admin():
    if st.session_state.get("role") != "admin":
        st.error("Kein Zugriff. Adminrechte erforderlich.")
        return

    _ensure_tables()
    _ensure_version_logged()

    page_header("Admin-Cockpit", "System- und Datenübersicht")

    tabs = st.tabs([
        "🏠 Übersicht",
        "🏢 Betrieb",
        "👤 Benutzer",
        "🧍 Mitarbeiter",
        "💰 Fixkosten",
        "🗂️ Datenbank",
        "💾 Backups"
    ])

    with tabs[0]:
        _render_home()
    with tabs[1]:
        _render_business_admin()

    # die restlichen Tabs belasse ich wie gehabt
    from modules.admin import (
        _render_user_admin,
        _render_employee_admin,
        _render_fixcost_admin,
        _render_db_overview,
        _render_backup_admin,
    )
