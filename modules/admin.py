import streamlit as st
import pandas as pd
import shutil
import time
import datetime
from pathlib import Path
from typing import Optional, List

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

        if not _table_exists(c, "meta"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

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


def _count_rows(table: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, table):
            return 0
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------- Backups (manuell, BCK_YYYYMMDD_HHMMSS.bak) ----------------
def _list_backups() -> List[Path]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(BACKUP_DIR.glob("BCK_*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _last_backup_time() -> Optional[datetime.datetime]:
    files = _list_backups()
    if not files:
        return None
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return datetime.datetime.fromtimestamp(latest.stat().st_mtime)


def _create_backup() -> Optional[Path]:
    """Erstellt ein manuelles Backup mit Timestamp."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"BCK_{ts}.bak"
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


# ---------------- UI Helpers (Badges / Status) ----------------
def _role_badge(role: str) -> str:
    colors = {
        "admin": "#e11d48",      # rose-600
        "barlead": "#0ea5e9",    # sky-500
        "user": "#10b981",       # emerald-500
        "inventur": "#f59e0b",   # amber-500
    }
    color = colors.get(role, "#6b7280")
    return f"<span style='background:{color}; color:white; padding:2px 6px; border-radius:999px; font-size:11px;'>{role}</span>"


def _pill(text: str, color: str = "#10b981") -> str:
    return f"<span style='background:{color}22; color:{color}; padding:2px 6px; border:1px solid {color}55; border-radius:999px; font-size:11px;'>{text}</span>"


def _status_badge_from_days(days: Optional[int]) -> tuple[str, str, str]:
    """
    Backup-Regeln: None => rot (kein Backup); <=5 grün; 6-7 gelb; >7 rot.
    """
    if days is None:
        return ("red", "Kein Backup", "Es wurde noch kein Backup gefunden.")
    if days <= 5:
        return ("green", "Aktuell", f"Letztes Backup ist {days} Tag(e) alt.")
    if days <= 7:
        return ("gold", "Bald fällig", f"Letztes Backup ist {days} Tag(e) alt (empfohlen: ≤5 Tage).")
    return ("red", "Überfällig", f"Letztes Backup ist {days} Tag(e) alt (kritisch).")


# ---------------- Übersicht / Dashboard ----------------
def _render_home():
    section_title("Systemstatus")

    # Live-Zahlen
    users_cnt = _count_rows("users")
    emp_cnt   = _count_rows("employees")
    fix_cnt   = _count_rows("fixcosts")

    # Backup-Status
    last_bkp_dt = _last_backup_time()
    days_since = None if last_bkp_dt is None else (datetime.date.today() - last_bkp_dt.date()).days
    badge_color, badge_label, badge_tip = _status_badge_from_days(days_since)

    # System-Hinweise
    issues = []
    if users_cnt == 0:
        issues.append("Keine Benutzer angelegt.")
    if emp_cnt == 0:
        issues.append("Keine Mitarbeiter angelegt.")
    if badge_color in ("gold", "red"):
        issues.append(badge_tip)

    # Eine Zeile: links kompakter Systemblock, rechts Inline-Details
    left, right = st.columns([5, 3])
    with left:
        today_str = datetime.date.today().strftime("%d.%m.%Y")
        st.markdown(
            f"""
            <div style='display:flex; gap:10px; align-items:center;
                        background:rgba(255,255,255,0.03); padding:8px 12px; border-radius:10px;'>
              <span style='display:inline-block; width:10px; height:10px; border-radius:50%; background:{badge_color};'></span>
              <div style='font-size:13px;'>
                <b>Status: {badge_label}</b>
                <span title="Systemprüfung und letzte Sicherung" style="opacity:0.7; cursor:help;">ⓘ</span><br>
                <span style='font-size:12px; opacity:0.85;'>Prüfung: {today_str}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with right:
        if issues:
            with st.expander("🔍 Details", expanded=False):
                for d in issues:
                    st.markdown(f"- {d}")
        else:
            st.caption("🟢 Keine Hinweise")

    # KPIs kompakt
    c1, c2, c3 = st.columns(3)
    c1.metric("Version", APP_VERSION)
    c2.metric("Benutzer", users_cnt)
    c3.metric("Mitarbeiter", emp_cnt)

    st.divider()

    # Backup-Status (separater Block – ohne Tabellen/Charts)
    section_title("Backup")
    last_text = "—"
    if last_bkp_dt:
        last_text = last_bkp_dt.strftime("%d.%m.%Y %H:%M")

    bl, br = st.columns([5, 3])
    with bl:
        st.markdown(
            f"""
            <div style='display:flex; gap:10px; align-items:center;
                        background:rgba(255,255,255,0.03); padding:8px 12px; border-radius:10px;'>
              <span style='display:inline-block; width:10px; height:10px; border-radius:50%; background:{badge_color};'></span>
              <div style='font-size:13px;'>
                <b>Backup-Status: {badge_label}</b>
                <span title="{badge_tip}" style="opacity:0.7; cursor:help;">ⓘ</span><br>
                <span style='font-size:12px; opacity:0.85;'>Letztes Backup: <b>{last_text}</b></span>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with br:
        if st.button("🧷 Backup jetzt erstellen", use_container_width=True):
            created = _create_backup()
            if created:
                st.success(f"Backup erstellt: {created.name}")
            time.sleep(1)
            st.rerun()

    st.markdown("---")

    # Changelog klein & aktuell
    section_title("📝 Änderungsprotokoll (Changelog)")
    with conn() as cn:
        df = pd.read_sql(
            "SELECT created_at, version, note FROM changelog ORDER BY datetime(created_at) DESC LIMIT 20",
            cn
        )
    if df.empty:
        st.info("Keine Einträge im Changelog.")
    else:
        for _, r in df.iterrows():
            st.markdown(
                f"<div style='font-size:12px;opacity:0.8;'><b>{r['version']}</b> – {r['created_at'][:16]}: {r['note']}</div>",
                unsafe_allow_html=True
            )


# ---------------- Benutzer ----------------
def _render_user_admin():
    section_title("👤 Benutzerverwaltung")

    with conn() as cn:
        c = cn.cursor()
        users = c.execute("SELECT id, username, role, email, first_name, last_name FROM users ORDER BY id").fetchall()

    with st.form("add_user_form"):
        c1, c2 = st.columns(2)
        new_user = c1.text_input("Benutzername")
        new_pw   = c2.text_input("Passwort", type="password")
        c3, c4 = st.columns(2)
        new_role = c3.selectbox("Rolle", ["admin", "barlead", "user", "inventur"])
        new_mail = c4.text_input("E-Mail")
        if st.form_submit_button("➕ Benutzer anlegen"):
            if new_user and new_pw:
                try:
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("""INSERT INTO users(username, role, email, passhash)
                                     VALUES(?,?,?, '')""",
                                  (new_user, new_role, new_mail))
                        cn.commit()
                    if change_password:
                        change_password(new_user, new_pw)
                    st.success(f"Benutzer '{new_user}' angelegt.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fehler beim Anlegen: {e}")
            else:
                st.warning("Benutzername und Passwort erforderlich.")

    st.divider()
    if not users:
        st.info("Noch keine Benutzer angelegt.")
    else:
        for uid, uname, role, email, first, last in users:
            role_tag = _role_badge(role)
            with st.expander(f"{uname}  ", expanded=False):
                # Rolle als Badge in der Kopfzeile anzeigen
                st.markdown(role_tag, unsafe_allow_html=True)

                a1, a2 = st.columns(2)
                e_username = a1.text_input("Benutzername (Login/Anzeige)", uname, key=f"u_username_{uid}")
                e_role  = a2.selectbox("Rolle", ["admin", "barlead", "user", "inventur"],
                                       index=["admin","barlead","user","inventur"].index(role),
                                       key=f"u_role_{uid}")
                b1, b2 = st.columns(2)
                e_first = b1.text_input("Vorname", first or "", key=f"u_first_{uid}")
                e_last  = b2.text_input("Nachname", last or "", key=f"u_last_{uid}")
                e_email = st.text_input("E-Mail", email or "", key=f"u_mail_{uid}")
                new_pw  = st.text_input("Neues Passwort (optional)", type="password", key=f"u_pw_{uid}")

                s1, s2 = st.columns(2)
                if s1.button("💾 Speichern", key=f"u_save_{uid}"):
                    try:
                        with conn() as cn:
                            c = cn.cursor()
                            # Username (UNIQUE) und restliche Felder aktualisieren
                            c.execute("""UPDATE users
                                         SET username=?, role=?, first_name=?, last_name=?, email=?
                                         WHERE id=?""",
                                      (e_username, e_role, e_first, e_last, e_email, uid))
                            cn.commit()
                        if new_pw:
                            change_password(e_username, new_pw)
                        st.success("Gespeichert.")
                    except Exception as e:
                        st.error(f"Fehler: {e}")

                if s2.button("🗑️ Löschen", key=f"u_del_{uid}"):
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("DELETE FROM users WHERE id=?", (uid,))
                        cn.commit()
                    st.warning(f"Benutzer '{uname}' gelöscht.")
                    st.rerun()


# ---------------- Mitarbeiter ----------------
def _render_employee_admin():
    section_title("🧍 Mitarbeiterverwaltung")

    with conn() as cn:
        c = cn.cursor()
        emps = c.execute("SELECT id, name, contract, hourly, is_barlead, bar_no FROM employees ORDER BY id").fetchall()

    with st.form("add_emp_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        contract = c2.selectbox("Vertrag", ["Teilzeit", "Vollzeit", "Geringfügig", "Fallweise"])
        c3, c4 = st.columns(2)
        hourly = c3.number_input("Stundenlohn (€)", min_value=0.0, step=1.0)
        barlead = c4.checkbox("Barleiter")
        if st.form_submit_button("➕ Mitarbeiter hinzufügen"):
            if not name:
                st.warning("Name ist erforderlich.")
            else:
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("""INSERT INTO employees(name, contract, hourly, is_barlead)
                                 VALUES(?,?,?,?)""",
                              (name, contract, hourly, int(barlead)))
                    cn.commit()
                st.success(f"Mitarbeiter '{name}' angelegt.")
                st.rerun()

    st.divider()
    if not emps:
        st.info("Noch keine Mitarbeiter.")
    else:
        for eid, name, contract, hourly, lead, barno in emps:
            with st.expander(name, expanded=False):
                c1, c2 = st.columns(2)
                e_con = c1.text_input("Vertrag", contract, key=f"e_con_{eid}")
                e_hour = c2.number_input("Stundenlohn (€)", value=float(hourly or 0.0), step=0.5, key=f"e_hour_{eid}")
                e_lead = st.checkbox("Barleiter", value=bool(lead), key=f"e_lead_{eid}")

                s1, s2 = st.columns(2)
                if s1.button("💾 Speichern", key=f"e_save_{eid}"):
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("""UPDATE employees SET contract=?, hourly=?, is_barlead=? WHERE id=?""",
                                  (e_con, e_hour, int(e_lead), eid))
                        cn.commit()
                    st.success("Gespeichert.")
                if s2.button("🗑️ Löschen", key=f"e_del_{eid}"):
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("DELETE FROM employees WHERE id=?", (eid,))
                        cn.commit()
                    st.warning(f"Mitarbeiter '{name}' gelöscht.")
                    st.rerun()


# ---------------- Fixkosten ----------------
def _render_fixcost_admin():
    section_title("💰 Fixkostenverwaltung")

    with conn() as cn:
        c = cn.cursor()
        costs = c.execute("SELECT id, name, amount, note, is_active FROM fixcosts ORDER BY id").fetchall()

    with st.form("add_fixcost"):
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Bezeichnung")
        amount = c2.number_input("Betrag (€)", min_value=0.0, step=10.0)
        note = st.text_input("Notiz (optional)")
        active = st.checkbox("Aktiv", value=True)
        if st.form_submit_button("➕ Fixkosten hinzufügen"):
            if not name:
                st.warning("Bezeichnung ist erforderlich.")
            else:
                with conn() as cn:
                    c = cn.cursor()
                    c.execute("""INSERT INTO fixcosts(name, amount, note, is_active)
                                 VALUES(?,?,?,?)""",
                              (name, float(amount), note, int(active)))
                    cn.commit()
                st.success("Fixkosten hinzugefügt.")
                st.rerun()

    st.divider()
    if not costs:
        st.info("Noch keine Fixkosten erfasst.")
    else:
        for fid, name, amount, note, active in costs:
            state_emoji = "🟢" if active else "⚪"
            with st.expander(f"{state_emoji} {name} – {amount:.2f} €", expanded=False):
                # Badge im Body
                st.markdown(
                    _pill("aktiv", "#10b981") if active else _pill("inaktiv", "#6b7280"),
                    unsafe_allow_html=True
                )
                st.write("")  # kleine Lücke

                c1, c2 = st.columns([2, 1])
                e_name = c1.text_input("Bezeichnung", value=name, key=f"fc_name_{fid}")
                e_amount = c2.number_input("Betrag (€)", value=float(amount or 0.0), step=10.0, key=f"fc_amount_{fid}")
                e_note = st.text_input("Notiz", value=note or "", key=f"fc_note_{fid}")
                e_active = st.checkbox("Aktiv", value=bool(active), key=f"fc_active_{fid}")
                s1, s2 = st.columns(2)
                if s1.button("💾 Speichern", key=f"fc_save_{fid}"):
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("""UPDATE fixcosts SET name=?, amount=?, note=?, is_active=? WHERE id=?""",
                                  (e_name, float(e_amount), e_note, int(e_active), fid))
                        cn.commit()
                    st.success("Gespeichert.")
                if s2.button("🗑️ Löschen", key=f"fc_del_{fid}"):
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute("DELETE FROM fixcosts WHERE id=?", (fid,))
                        cn.commit()
                    st.warning(f"Fixkosten '{name}' gelöscht.")
                    st.rerun()


# ---------------- Datenbank-Übersicht ----------------
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


# ---------------- Backup-Verwaltung ----------------
def _render_backup_admin():
    section_title("💾 Datenbank-Backups")

    # Letztes Backup prominent anzeigen
    lb = _last_backup_time()
    last_text = lb.strftime("%d.%m.%Y %H:%M") if lb else "—"
    st.caption(f"Letztes Backup: **{last_text}**")

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
        "👤 Benutzer",
        "🧍 Mitarbeiter",
        "💰 Fixkosten",
        "🗂️ Datenbank",
        "💾 Backups"
    ])

    with tabs[0]:
        _render_home()
    with tabs[1]:
        _render_user_admin()
    with tabs[2]:
        _render_employee_admin()
    with tabs[3]:
        _render_fixcost_admin()
    with tabs[4]:
        _render_db_overview()
    with tabs[5]:
        _render_backup_admin()

    st.markdown("---")
    st.caption(f"© 2025 Roman Petek – {APP_NAME} {APP_VERSION}")
