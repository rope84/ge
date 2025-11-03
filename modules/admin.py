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


# ========================== CHANGELOG ==========================
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


# ========================== HILFSFUNKTIONEN ==========================
def _table_exists(c, name: str) -> bool:
    return c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


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
        c.executemany("INSERT INTO changelog(created_at, version, note) VALUES(?,?,?)", rows)
        cn.commit()


def _ensure_version_logged():
    last = _get_meta("last_seen_version")
    if last != APP_VERSION:
        notes = DEFAULT_CHANGELOG_NOTES.get(APP_VERSION, [f"Update auf {APP_VERSION}"])
        _insert_changelog(APP_VERSION, notes)
        _set_meta("last_seen_version", APP_VERSION)


# ========================== BACKUP FUNKTIONEN ==========================
def _list_backups():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(BACKUP_DIR.glob("BCK_*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)


def _create_backup() -> Optional[Path]:
    """Erstellt maximal 1 Backup pro Tag."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today_tag = datetime.date.today().strftime("%Y%m%d")

    existing = list(BACKUP_DIR.glob(f"BCK_{today_tag}.bak"))
    if existing:
        st.warning(f"⚠️ Backup für heute ({today_tag}) existiert bereits: {existing[0].name}")
        return None

    target = BACKUP_DIR / f"BCK_{today_tag}.bak"
    shutil.copy(DB_PATH, target)
    return target


def _restore_backup(file_path: Path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    safe = BACKUP_DIR / f"pre_restore_{int(time.time())}.bak"
    try:
        shutil.copy(DB_PATH, safe)
    except Exception:
        pass
    shutil.copy(file_path, DB_PATH)


def _format_size(bytes_: int) -> str:
    return f"{bytes_ / (1024 * 1024):.1f} MB"


# ========================== SYSTEMSTATUS ==========================
def _system_status():
    users_cnt = _count_rows("users")
    emp_cnt = _count_rows("employees")
    fix_cnt = _count_rows("fixcosts")
    bkp_cnt = len(_list_backups())

    status = "🟢 System OK"
    if users_cnt == 0 or emp_cnt == 0:
        status = "🟡 Eingeschränkt – Daten unvollständig"
    if bkp_cnt == 0:
        status = "🔴 Kritisch – Keine Backups gefunden"

    with st.container():
        st.markdown(
            f"""
            <div style='background-color:#1e1e1e;padding:10px 20px;border-radius:10px;margin-bottom:15px'>
                <h4 style='color:#ccc;margin:0'>Systemstatus: {status}</h4>
            </div>
            """,
            unsafe_allow_html=True
        )

    return users_cnt, emp_cnt, fix_cnt, bkp_cnt


def _count_rows(table: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, table):
            return 0
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ========================== ADMIN START ==========================
def _render_home():
    section_title("Systemstatus")
    users_cnt, emp_cnt, fix_cnt, bkp_cnt = _system_status()

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Version", APP_VERSION)
    c2.metric("Benutzer", users_cnt)
    c3.metric("Mitarbeiter", emp_cnt)
    c4.metric("Backups", bkp_cnt)

    st.markdown("---")

    # Charts
    left, right = st.columns(2)
    with left:
        df_kpi = pd.DataFrame({
            "Kategorie": ["Benutzer", "Mitarbeiter", "Fixkosten"],
            "Anzahl": [users_cnt, emp_cnt, fix_cnt]
        })
        fig = px.pie(df_kpi, names="Kategorie", values="Anzahl", hole=0.4, title="Verteilung der Kerndaten")
        st.plotly_chart(fig, use_container_width=True, theme="streamlit")

    with right:
        bfiles = _list_backups()[:10]
        if bfiles:
            data = [{"Backup": f.name[-12:], "Größe (MB)": round(f.stat().st_size / (1024 * 1024), 2)} for f in bfiles]
            fig2 = px.bar(pd.DataFrame(data), x="Backup", y="Größe (MB)", title="Letzte Backups (Größe in MB)")
            st.plotly_chart(fig2, use_container_width=True, theme="streamlit")
        else:
            st.info("Noch keine Backups vorhanden.")

    st.markdown("---")

    # Changelog
    section_title("📝 Änderungsprotokoll")
    today = datetime.date.today().strftime("%d.%m.%Y")

    with conn() as cn:
        df = pd.read_sql("SELECT created_at, version, note FROM changelog ORDER BY datetime(created_at) DESC LIMIT 20", cn)

    if df.empty:
        st.info("Noch keine Changelog-Einträge vorhanden.")
    else:
        for _, r in df.iterrows():
            st.markdown(
                f"<div style='font-size:12px;opacity:0.85;'><b>{r['version']}</b> · {r['created_at'][:16]} — {r['note']}</div>",
                unsafe_allow_html=True,
            )

    st.caption(f"Letzte Prüfung: {today} | Datenbankpfad: `{DB_PATH}`")


# ========================== ADMIN HAUPTFUNKTION ==========================
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

    # -------- Übersicht --------
    with tabs[0]:
        _render_home()

    # -------- Benutzer --------
    with tabs[1]:
        section_title("👤 Benutzerverwaltung")
        _render_user_admin()

    # -------- Mitarbeiter --------
    with tabs[2]:
        section_title("🧍 Mitarbeiterverwaltung")
        _render_employee_admin()

    # -------- Fixkosten --------
    with tabs[3]:
        section_title("💰 Fixkostenverwaltung")
        _render_fixcost_admin()

    # -------- Datenbank --------
    with tabs[4]:
        _render_db_overview()

    # -------- Backups --------
    with tabs[5]:
        _render_backup_admin()

    st.markdown("---")
    st.caption(f"© 2025 Roman Petek – {APP_NAME} {APP_VERSION}")


# ========================== MODULE: BENUTZER / MITARBEITER / FIXKOSTEN / BACKUP ==========================
def _render_user_admin():
    with conn() as cn:
        c = cn.cursor()
        users = c.execute("SELECT id, username, role, email, first_name, last_name FROM users ORDER BY id").fetchall()

    with st.form("add_user_form"):
        c1, c2 = st.columns(2)
        new_user = c1.text_input("Benutzername")
        new_pw = c2.text_input("Passwort", type="password")
        c3, c4 = st.columns(2)
        new_role = c3.selectbox("Rolle", ["admin", "barlead", "user", "inventur"])
        new_mail = c4.text_input("E-Mail")
        if st.form_submit_button("➕ Benutzer anlegen"):
            if new_user and new_pw:
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("INSERT INTO users(username, role, email, passhash) VALUES(?,?,?, '')",
                              (new_user, new_role, new_mail))
                    cn.commit()
                if change_password:
                    change_password(new_user, new_pw)
                st.success(f"Benutzer '{new_user}' angelegt.")
                st.rerun()

    st.divider()
    for uid, uname, role, email, first, last in users:
        with st.expander(f"{uname} ({role})"):
            e_first = st.text_input("Vorname", first or "", key=f"u_first_{uid}")
            e_last = st.text_input("Nachname", last or "", key=f"u_last_{uid}")
            e_role = st.selectbox("Rolle", ["admin", "barlead", "user", "inventur"], index=["admin","barlead","user","inventur"].index(role), key=f"u_role_{uid}")
            new_pw = st.text_input("Neues Passwort", type="password", key=f"pw_{uid}")
            s1, s2 = st.columns(2)
            if s1.button("💾 Speichern", key=f"save_{uid}"):
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("UPDATE users SET first_name=?, last_name=?, role=? WHERE id=?", (e_first, e_last, e_role, uid))
                    cn.commit()
                if new_pw:
                    change_password(uname, new_pw)
                st.success("Gespeichert.")
            if s2.button("🗑️ Löschen", key=f"del_{uid}"):
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("DELETE FROM users WHERE id=?", (uid,))
                    cn.commit()
                st.warning(f"Benutzer '{uname}' gelöscht.")
                st.rerun()


def _render_employee_admin():
    with conn() as cn:
        c = cn.cursor()
        emps = c.execute("SELECT id, name, contract, hourly, is_barlead, bar_no FROM employees ORDER BY id").fetchall()

    with st.form("add_emp_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        contract = c2.selectbox("Vertrag", ["Teilzeit", "Vollzeit", "Geringfügig"])
        c3, c4 = st.columns(2)
        hourly = c3.number_input("Stundenlohn (€)", min_value=0.0, step=1.0)
        barlead = c4.checkbox("Barleiter")
        if st.form_submit_button("➕ Mitarbeiter hinzufügen"):
            with conn() as cn:
                c = cn.cursor()
                c.execute("INSERT INTO employees(name, contract, hourly, is_barlead) VALUES(?,?,?,?)",
                          (name, contract, hourly, int(barlead)))
                cn.commit()
            st.success(f"Mitarbeiter '{name}' angelegt.")
            st.rerun()

    st.divider()
    for eid, name, contract, hourly, lead, barno in emps:
        with st.expander(name):
            e_con = st.text_input("Vertrag", contract, key=f"con_{eid}")
            e_hour = st.number_input("Stundenlohn (€)", value=float(hourly), step=0.5, key=f"hour_{eid}")
            e_lead = st.checkbox("Barleiter", value=bool(lead), key=f"lead_{eid}")
            s1, s2 = st.columns(2)
            if s1.button("💾 Speichern", key=f"emp_save_{eid}"):
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("UPDATE employees SET contract=?, hourly=?, is_barlead=? WHERE id=?",
                              (e_con, e_hour, int(e_lead), eid))
                    cn.commit()
                st.success("Gespeichert.")
            if s2.button("🗑️ Löschen", key=f"emp_del_{eid}"):
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("DELETE FROM employees WHERE id=?", (eid,))
                    cn.commit()
                st.warning(f"Mitarbeiter '{name}' gelöscht.")
                st.rerun()


def _render_fixcost_admin():
    with conn() as cn:
        c = cn.cursor()
        costs = c.execute("SELECT id, name, amount, note, is_active FROM fixcosts ORDER BY id").fetchall()

    with st.form("add_fixcost"):
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Bezeichnung")
        amount = c2.number_input("Betrag (€)", min_value=0.0, step=50.0)
        note = st.text_input("Notiz (optional)")
        active = st.checkbox("Aktiv", value=True)
        if st.form_submit_button("➕ Fixkosten hinzufügen"):
            with conn() as cn:
                c = cn.cursor()
                c.execute("INSERT INTO fixcosts(name, amount, note, is_active) VALUES(?,?,?,?)",
                          (name, amount, note, int(active)))
                cn.commit()
            st.success("Fixkosten hinzugefügt.")
            st.rerun()

    st.divider()
    for fid, name, amount, note, active in costs:
        with st.expander(f"{name} – {amount:.2f} €"):
            e_name = st.text_input("Bezeichnung", name, key=f"fc_name_{fid}")
            e_amount = st.number_input("Betrag (€)", value=float(amount), step=10.0, key=f"fc_amount_{fid}")
            e_note = st.text_input("Notiz", note or "", key=f"fc_note_{fid}")
            e_active = st.checkbox("Aktiv", value=bool(active), key=f"fc_active_{fid}")
            s1, s2 = st.columns(2)
            if s1.button("💾 Speichern", key=f"fc_save_{fid}"):
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("UPDATE fixcosts SET name=?, amount=?, note=?, is_active=? WHERE id=?",
                              (e_name, e_amount, e_note, int(e_active), fid))
                    cn.commit()
                st.success("Gespeichert.")
            if s2.button("🗑️ Löschen", key=f"fc_del_{fid}"):
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("DELETE FROM fixcosts WHERE id=?", (fid,))
                    cn.commit()
                st.warning(f"Fixkosten '{name}' gelöscht.")
                st.rerun()


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
        st.download_button(
            "📤 CSV exportieren",
            csv,
            file_name=f"{selected_table}.csv",
            mime="text/csv",
            use_container_width=True,
        )


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
