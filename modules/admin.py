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

# ---- Standard-Änderungsnotizen
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

# ---------------- Hilfsfunktionen ----------------
def _table_exists(c, name: str) -> bool:
    return c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None


def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()

        # users
        if not _table_exists(c, "users"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    email TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    passhash TEXT NOT NULL DEFAULT ''
                )
            """)

        # employees
        if not _table_exists(c, "employees"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    contract TEXT NOT NULL,
                    hourly REAL NOT NULL DEFAULT 0,
                    is_barlead INTEGER NOT NULL DEFAULT 0,
                    bar_no INTEGER
                )
            """)

        # fixcosts
        if not _table_exists(c, "fixcosts"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS fixcosts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL DEFAULT 0,
                    note TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
            """)

        # meta
        if not _table_exists(c, "meta"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

        # changelog
        if not _table_exists(c, "changelog"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS changelog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    version TEXT NOT NULL,
                    note TEXT NOT NULL
                )
            """)

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
            "INSERT INTO changelog(created_at, version, note) VALUES(?,?,?)",
            rows
        )
        cn.commit()


def _ensure_version_logged():
    last = _get_meta("last_seen_version")
    if last != APP_VERSION:
        notes = DEFAULT_CHANGELOG_NOTES.get(APP_VERSION, [f"Update auf {APP_VERSION}"])
        _insert_changelog(APP_VERSION, notes)
        _set_meta("last_seen_version", APP_VERSION)


# ---------------- Backups ----------------
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
    """Erstellt ein Backup, aber maximal 1x pro Tag."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().strftime("%Y%m%d")
    existing = [f for f in BACKUP_DIR.glob(f"BCK_{today}*.bak")]
    if existing:
        st.warning("Heute wurde bereits ein Backup erstellt.")
        return None

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"BCK_{ts}.bak"
    shutil.copy(DB_PATH, target)
    return target


def _format_size(bytes_: int) -> str:
    mb = bytes_ / (1024 * 1024)
    return f"{mb:.1f} MB"


def _count_rows(table: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, table):
            return 0
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------- Dashboard (Übersicht) ----------------
def _render_home():
    section_title("Systemüberblick")

    # Kennzahlen
    users_cnt = _count_rows("users")
    emp_cnt   = _count_rows("employees")
    fix_cnt   = _count_rows("fixcosts")
    bkp_cnt   = len(_list_backups())
    today_str = datetime.date.today().strftime("%d.%m.%Y")

    # ---- Ampelstatus ----
    status_color = "green"
    warn_details = []

    if users_cnt == 0 or emp_cnt == 0:
        status_color = "yellow"
        warn_details.append("Keine Benutzer oder Mitarbeiter angelegt.")
    if bkp_cnt == 0:
        status_color = "red"
        warn_details.append("Kein Backup vorhanden.")
    else:
        last_bkp = max(f.stat().st_mtime for f in _list_backups())
        days_old = (datetime.date.today() - datetime.date.fromtimestamp(last_bkp)).days
        if days_old > 1:
            status_color = "yellow"
            warn_details.append(f"Letztes Backup ist {days_old} Tage alt.")

    # Textstatus
    if status_color == "green":
        status_text = "🟢 Systemstatus: Alles in Ordnung."
    elif status_color == "yellow":
        status_text = "🟡 Systemstatus: Es gibt Hinweise."
    else:
        status_text = "🔴 Systemstatus: Handlungsbedarf!"

    # Anzeige
    st.markdown(
        f"""
        <div style='border-left:6px solid {status_color};
                    background-color:rgba(255,255,255,0.03);
                    padding:10px 14px;
                    border-radius:10px;
                    font-size:13px;
                    margin-bottom:1rem;'>
            <b>{status_text}</b><br>
            <span style='font-size:12px;opacity:0.8;'>Letzte Prüfung: {today_str}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    if status_color in ["yellow", "red"]:
        if st.button("🔍 Details anzeigen"):
            st.markdown(
                "<br>".join([f"– {d}" for d in warn_details]),
                unsafe_allow_html=True
            )

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Version", APP_VERSION)
    c2.metric("Benutzer", users_cnt)
    c3.metric("Mitarbeiter", emp_cnt)
    c4.metric("Backups", bkp_cnt)

    st.divider()

    # Charts
    left, right = st.columns(2)
    with left:
        df = pd.DataFrame({
            "Kategorie": ["Benutzer", "Mitarbeiter", "Fixkosten"],
            "Anzahl": [users_cnt, emp_cnt, fix_cnt]
        })
        fig = px.pie(df, names="Kategorie", values="Anzahl", hole=0.5, title="Verteilung Kernobjekte")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        files = _list_backups()[:10]
        if files:
            data = [{"Backup": f.name[-16:], "Größe (MB)": round(f.stat().st_size / (1024*1024), 2)} for f in files]
            fig2 = px.bar(pd.DataFrame(data), x="Backup", y="Größe (MB)", title="Letzte Backups")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Noch keine Backups vorhanden.")

    st.markdown("---")

    # Changelog
    section_title("📝 Änderungsprotokoll (Changelog)")
    with conn() as cn:
        df = pd.read_sql("SELECT created_at, version, note FROM changelog ORDER BY datetime(created_at) DESC LIMIT 20", cn)
    if df.empty:
        st.info("Keine Einträge im Changelog.")
    else:
        for _, r in df.iterrows():
            st.markdown(f"<div style='font-size:12px;opacity:0.8;'><b>{r['version']}</b> – {r['created_at'][:16]}: {r['note']}</div>", unsafe_allow_html=True)


# ---------------- Datenbank-Tab ----------------
def _render_db_overview():
    section_title("🗂️ Datenbank – Übersicht & Export")

    with conn() as cn:
        c = cn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]

    if not tables:
        st.info("Keine Tabellen vorhanden.")
        return

    selected_table = st.selectbox("Tabelle auswählen", tables)
    if selected_table:
        with conn() as cn:
            df = pd.read_sql(f"SELECT * FROM {selected_table}", cn)
        st.dataframe(df, use_container_width=True, height=420)

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📤 CSV exportieren", csv, file_name=f"{selected_table}.csv", mime="text/csv")


# ---------------- Backup-Tab ----------------
def _render_backup_admin():
    section_title("💾 Datenbank-Backups")
    col_a, col_b = st.columns([1, 1])

    if col_a.button("🧷 Backup jetzt erstellen", use_container_width=True):
        created = _create_backup()
        if created:
            st.success(f"Backup erstellt: {created.name}")
        time.sleep(1)
        st.rerun()

    backups = _list_backups()
    if not backups:
        st.info("Keine Backups gefunden.")
        return

    opt = {f.name: f for f in backups}
    sel = st.selectbox("Backup auswählen", list(opt.keys()))
    chosen = opt[sel]
    st.write(f"📅 {time.ctime(chosen.stat().st_mtime)}")
    st.write(f"📁 {chosen}")
    st.write(f"💾 Größe: {_format_size(chosen.stat().st_size)}")

    ok = st.checkbox("Ich bestätige die Wiederherstellung dieses Backups.")
    if col_b.button("🔄 Backup wiederherstellen", disabled=not ok, use_container_width=True):
        with st.spinner("Backup wird wiederhergestellt..."):
            _restore_backup(chosen)
            time.sleep(1.0)
        st.success("✅ Backup wiederhergestellt. Bitte App neu starten.")


# ---------------- Hauptfunktion ----------------
def render_admin():
    if st.session_state.get("role") != "admin":
        st.error("Kein Zugriff. Adminrechte erforderlich.")
        return

    _ensure_tables()
    _ensure_version_logged()

    page_header("Admin-Cockpit", "System- und Datenübersicht")

    tabs = st.tabs(["🏠 Übersicht", "👤 Benutzer", "🧍 Mitarbeiter", "💰 Fixkosten", "🗂️ Datenbank", "💾 Backups"])

    with tabs[0]:
        _render_home()
    with tabs[4]:
        _render_db_overview()
    with tabs[5]:
        _render_backup_admin()

    st.markdown("---")
    st.caption(f"© 2025 Roman Petek – {APP_NAME} {APP_VERSION}")
