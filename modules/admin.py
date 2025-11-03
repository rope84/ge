import streamlit as st
import pandas as pd
import shutil
import time
import datetime
import plotly.express as px
from pathlib import Path
from typing import Optional, List

from core.db import BACKUP_DIR, DB_PATH, conn
from core.ui_theme import page_header, section_title, metric_card
from core.auth import change_password
from core.config import APP_NAME, APP_VERSION

# ---- Default-Änderungsnotizen
DEFAULT_CHANGELOG_NOTES = {
    "Beta 1": [
        "Neues einheitliches UI-Theme & aufgeräumte Navigation",
        "Admin-Cockpit mit Startseite & KPIs",
        "Verbessertes Profil-Modul inkl. Passwort ändern",
        "Inventur mit Monatslogik & PDF-Export",
        "Abrechnung poliert: Garderobe-Logik, Voucher-Einbezug",
        "Datenbank-Backups inkl. Restore-Funktion"
    ]
}

# ------------------- Hilfsfunktionen -------------------
def _table_exists(c, name: str) -> bool:
    return c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None

def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()
        tables = {
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
        for name, sql in tables.items():
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

def _insert_changelog(version: str, notes: List[str]):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        rows = [(now, version, note) for note in notes]
        c.executemany(
            "INSERT INTO changelog(created_at, version, note) VALUES(?,?,?)", rows
        )
        cn.commit()

def _ensure_version_logged():
    last = _get_meta("last_seen_version")
    if last != APP_VERSION:
        notes = DEFAULT_CHANGELOG_NOTES.get(APP_VERSION, [f"Update auf {APP_VERSION}"])
        _insert_changelog(APP_VERSION, notes)
        _set_meta("last_seen_version", APP_VERSION)

# ------------------- Backups -------------------
def _list_backups():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(BACKUP_DIR.glob("BCK_*.bak"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files

def _restore_backup(file_path: Path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    safe = BACKUP_DIR / f"pre_restore_{ts}.bak"
    try:
        shutil.copy(DB_PATH, safe)
    except Exception:
        pass
    shutil.copy(file_path, DB_PATH)

def _create_backup() -> Optional[Path]:
    """Erstellt ein Backup – aber nur einmal täglich."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today_tag = datetime.date.today().strftime("%Y%m%d")

    # Prüfen, ob heutiges Backup schon existiert
    existing = list(BACKUP_DIR.glob(f"BCK_{today_tag}.bak"))
    if existing:
        st.warning(f"⚠️ Backup für heute ({today_tag}) existiert bereits: {existing[0].name}")
        return None

    target = BACKUP_DIR / f"BCK_{today_tag}.bak"
    shutil.copy(DB_PATH, target)
    return target

def _format_size(bytes_: int) -> str:
    mb = bytes_ / (1024 * 1024)
    return f"{mb:.1f} MB"

# ------------------- Zähler -------------------
def _count_rows(table: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, table):
            return 0
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

# ------------------- Admin-Startseite -------------------
def _render_home():
    # ---------- Systemstatus (KPI + Mini-Charts) ----------
    section_title("Systemstatus")

    users_cnt = _count_rows("users")
    emp_cnt   = _count_rows("employees")
    fix_cnt   = _count_rows("fixcosts")
    bkp_cnt   = len(_list_backups())
    today_str = datetime.date.today().strftime("%d.%m.%Y")

    # KPI Reihe
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Version", APP_VERSION, "Aktiver Build")
    with c2:
        metric_card("Benutzer", f"{users_cnt}", "Registrierte Accounts")
    with c3:
        metric_card("Mitarbeiter", f"{emp_cnt}", "Erfasste Mitarbeiter")
    with c4:
        metric_card("Backups", f"{bkp_cnt}", "Gespeicherte Sicherungen")

    # Charts
    left, right = st.columns(2)
    with left:
        df_kpi = pd.DataFrame({
            "Kategorie": ["Benutzer", "Mitarbeiter", "Fixkosten"],
            "Anzahl": [users_cnt, emp_cnt, fix_cnt]
        })
        fig = px.pie(df_kpi, names="Kategorie", values="Anzahl", hole=0.5,
                     title="Verteilung Kernobjekte")
        st.plotly_chart(fig, use_container_width=True, theme="streamlit")

    with right:
        bfiles = _list_backups()[:10]
        if bfiles:
            data = [{
                "Backup": f.name,
                "Größe (MB)": round(f.stat().st_size / (1024 * 1024), 2)
            } for f in bfiles]
            fig2 = px.bar(pd.DataFrame(data), x="Backup", y="Größe (MB)",
                          title="Letzte Backups", labels={"Backup": "Dateiname"})
            st.plotly_chart(fig2, use_container_width=True, theme="streamlit")
        else:
            st.info("Noch keine Backups vorhanden.")

    st.markdown("---")

    # ---------- Changelog kompakt ----------
    section_title("📝 Änderungsprotokoll (Changelog)")
    refresh = st.button("🔄 Aktualisieren", use_container_width=True)
    with conn() as cn:
        df = pd.read_sql(
            "SELECT created_at, version, note FROM changelog ORDER BY datetime(created_at) DESC LIMIT 25",
            cn
        )
    if df.empty:
        st.info("Noch keine Changelog-Einträge vorhanden.")
    else:
        for _, r in df.iterrows():
            st.markdown(
                f"<div style='font-size:12px; opacity:0.85;'>"
                f"<b>{r['version']}</b> · {r['created_at'][:16]} — {r['note']}</div>",
                unsafe_allow_html=True
            )
    st.caption(f"Letzte Prüfung: {today_str}")

# ------------------- Haupt-Render -------------------
def render_admin():
    if st.session_state.get("role") != "admin":
        st.error("Kein Zugriff. Adminrechte erforderlich.")
        return

    _ensure_tables()
    _ensure_version_logged()

    page_header("Admin-Cockpit", "System- und Datenübersicht")

    tabs = st.tabs([
        "🏠 Übersicht",
        "👤 Benutzer",
        "🧍 Mitarbeiter",
        "💰 Fixkosten",
        "🗂️ Datenbank",
        "💾 Backups"
    ])

    with tabs[0]:
        _render_home()

    # --- Platzhalter für Benutzer/Mitarbeiter/Fixkosten Tabs ---
    with tabs[1]:
        section_title("👤 Benutzerverwaltung")
        st.info("Hier folgt die Benutzerverwaltung (in Entwicklung).")

    with tabs[2]:
        section_title("🧍 Mitarbeiterverwaltung")
        st.info("Hier folgt die Mitarbeiterverwaltung (in Entwicklung).")

    with tabs[3]:
        section_title("💰 Fixkostenverwaltung")
        st.info("Hier folgt die Fixkostenverwaltung (in Entwicklung).")

    # --- TAB Datenbank ---
    with tabs[4]:
        section_title("🗂️ Datenbank – Übersicht & Export")
        # bleibt unverändert, du kannst aus deiner alten Version übernehmen

    # --- TAB Backups ---
    with tabs[5]:
        section_title("💾 Datenbank-Backups")
        col_a, col_b = st.columns([1, 1])
        if col_a.button("🧷 Backup jetzt erstellen", use_container_width=True):
            created = _create_backup()
            if created:
                st.success(f"✅ Neues Backup erstellt: {created.name}")
            else:
                st.stop()

        backups = _list_backups()
        if not backups:
            st.info("Keine Backups gefunden.")
        else:
            opt = {f.name: f for f in backups}
            sel = st.selectbox("Backup auswählen", list(opt.keys()))
            chosen = opt[sel]
            st.write(f"📅 {time.ctime(chosen.stat().st_mtime)}")
            st.write(f"📁 {chosen}")
            ok = st.checkbox("Ich bestätige die Wiederherstellung dieses Backups.")
            if col_b.button("🔄 Wiederherstellen", disabled=not ok, use_container_width=True):
                with st.spinner("Backup wird wiederhergestellt..."):
                    _restore_backup(chosen)
                    time.sleep(1.0)
                st.success("✅ Backup wiederhergestellt. Bitte App neu starten.")

    st.markdown("---")
    st.caption(f"© 2025 Roman Petek – {APP_NAME} {APP_VERSION}")
