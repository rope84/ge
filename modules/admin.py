# admin.py
import streamlit as st
import pandas as pd
import shutil
import time
import datetime
from pathlib import Path
from typing import Optional, List

from core.db import BACKUP_DIR, DB_PATH, conn
from core.ui_theme import page_header, section_title, metric_card
from core.auth import change_password  # zentral importiert (keine try/except-Hacks)

APP_VERSION = "Gastro Essentials – Beta 1"

# ---- Default-Änderungsnotizen pro Version
DEFAULT_CHANGELOG_NOTES = {
    "Gastro Essentials – Beta 1": [
        "Neues einheitliches UI-Theme & aufgeräumte Navigation",
        "Admin-Cockpit mit Startseite & KPIs",
        "Verbessertes Profil-Modul inkl. Passwort ändern",
        "Inventur mit Monatslogik & PDF-Export",
        "Abrechnung poliert: Garderobe-Logik, Voucher-Einbezug",
        "Datenbank-Backups inkl. Restore-Funktion"
    ]
}

# ------------------- Hilfsfunktionen: DB-Tabellen -------------------
def _table_exists(c, name: str) -> bool:
    return c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone() is not None

def _ensure_tables():
    """Sicherstellen, dass essentielle Tabellen existieren."""
    with conn() as cn:
        c = cn.cursor()

        # users (robuster: hier anlegen; seed_admin_if_empty kümmert sich um Inhalte)
        if not _table_exists(c, "users"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT NOT NULL UNIQUE,
                    role        TEXT NOT NULL,
                    email       TEXT,
                    first_name  TEXT,
                    last_name   TEXT,
                    passhash    TEXT NOT NULL DEFAULT ''
                )
            """)

        # employees
        if not _table_exists(c, "employees"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    contract    TEXT NOT NULL,
                    hourly      REAL NOT NULL DEFAULT 0,
                    is_barlead  INTEGER NOT NULL DEFAULT 0,
                    bar_no      INTEGER
                )
            """)

        # fixcosts
        if not _table_exists(c, "fixcosts"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS fixcosts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name      TEXT NOT NULL,
                    amount    REAL NOT NULL DEFAULT 0,
                    note      TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
            """)

        # meta (Key/Value)
        if not _table_exists(c, "meta"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

        # changelog
        if not _table_exists(c, "changelog"):
            c.execute("""
                CREATE TABLE IF NOT EXISTS changelog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    version    TEXT NOT NULL,
                    note       TEXT NOT NULL
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
    """Trägt bei Versionswechsel automatisch einen Changelog-Eintrag ein."""
    last = _get_meta("last_seen_version")
    if last != APP_VERSION:
        notes = DEFAULT_CHANGELOG_NOTES.get(APP_VERSION, [f"Update auf {APP_VERSION}"])
        _insert_changelog(APP_VERSION, notes)
        _set_meta("last_seen_version", APP_VERSION)

# ------------------- Backups -------------------
def _list_backups():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(BACKUP_DIR.glob("*.bak_*"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files

def _restore_backup(file_path: Path):
    """Backup wiederherstellen; vorher aktuelle DB sichern."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    safe = BACKUP_DIR / f"pre_restore_{ts}.bak"
    try:
        shutil.copy(DB_PATH, safe)
    except Exception:
        pass
    shutil.copy(file_path, DB_PATH)

def _create_backup() -> Path:
    """Manuelles Backup erzeugen."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / f"{DB_PATH.name}.bak_{ts}"
    shutil.copy(DB_PATH, target)
    return target

# ------------------- Zähler -------------------
def _count_rows(table: str) -> int:
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, table):
            return 0
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

# ------------------- Admin-Startseite -------------------
def _render_home():
    # Header + Intro
    page_header("Admin-Cockpit", "System- und Datenübersicht")
    section_title("Willkommen")
    st.markdown(
        "Willkommen im **Gastro Essentials Admin-Cockpit**. "
        "Hier verwaltest du Benutzer, Mitarbeiter, Fixkosten, Datenbanken und Backups."
    )

    # KPIs
    section_title("Systemstatus")
    a1, a2, a3 = st.columns(3)
    b1, b2, b3 = st.columns(3)
    with a1:
        metric_card("Version", APP_VERSION, "Aktiver Build")
    with a2:
        metric_card("Benutzer", str(_count_rows("users")), "Registrierte Accounts")
    with a3:
        metric_card("Mitarbeiter", str(_count_rows("employees")), "Erfasste Mitarbeiter")
    with b1:
        metric_card("Fixkosten", str(_count_rows("fixcosts")), "Monatliche Posten")
    with b2:
        metric_card("Backups", str(len(_list_backups())), "Gefundene .bak-Dateien")
    with b3:
        metric_card("Letztes Update", datetime.date.today().strftime("%d.%m.%Y"), "Automatisch erkannt")

    st.markdown("---")
    section_title("📝 Änderungsprotokoll (Changelog)")
    with conn() as cn:
        df = pd.read_sql(
            "SELECT created_at, version, note FROM changelog ORDER BY datetime(created_at) DESC LIMIT 20",
            cn
        )
    if df.empty:
        st.info("Noch keine Changelog-Einträge vorhanden.")
    else:
        for _, r in df.iterrows():
            st.markdown(f"- **{r['version']}** · {r['created_at'][:16]} — {r['note']}")

    st.caption(f"Datenbankpfad: `{DB_PATH}`")

# ------------------- Haupt-Render -------------------
def render_admin():
    # Guard – doppelt hält besser
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

    # ------------------- TAB 1: START/ÜBERSICHT -------------------
    with tabs[0]:
        _render_home()

    # ------------------- TAB 2: BENUTZER -------------------
    with tabs[1]:
        section_title("👤 Benutzerverwaltung")

        with st.form("add_user_form"):
            c1, c2, c3 = st.columns([1, 1, 1])
            new_user = c1.text_input("Benutzername")
            new_role = c2.selectbox("Rolle", ["admin", "barlead", "user", "inventur"])
            new_mail = c3.text_input("E-Mail")
            d1, d2 = st.columns(2)
            new_first = d1.text_input("Vorname")
            new_last = d2.text_input("Nachname")
            new_pw = st.text_input("Passwort (wird gesetzt)", type="password")
            if st.form_submit_button("Benutzer anlegen"):
                if not new_user or not new_pw:
                    st.warning("Benutzername und Passwort erforderlich.")
                else:
                    try:
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute(
                                """INSERT INTO users(username, role, email, first_name, last_name, passhash)
                                   VALUES(?,?,?,?,?, '')""",
                                (new_user, new_role, new_mail, new_first, new_last)
                            )
                            cn.commit()
                        ok = change_password(new_user, new_pw)
                        if ok:
                            st.success(f"✅ Benutzer '{new_user}' angelegt & Passwort gesetzt.")
                        else:
                            st.warning(f"Benutzer '{new_user}' angelegt. ⚠️ Passwort konnte nicht gesetzt werden.")
                    except Exception as e:
                        st.error(f"Fehler: {e}")

        st.divider()
        with conn() as cn:
            c = cn.cursor()
            users = c.execute(
                "SELECT id, username, role, email, first_name, last_name FROM users ORDER BY id"
            ).fetchall()
        if not users:
            st.info("Noch keine Benutzer angelegt.")
        else:
            for uid, uname, role, email, first, last in users:
                with st.expander(f"{uname} ({role})"):
                    a, b, cx = st.columns(3)
                    e_first = a.text_input("Vorname", value=first or "", key=f"u_first_{uid}")
                    e_last = b.text_input("Nachname", value=last or "", key=f"u_last_{uid}")
                    e_mail = cx.text_input("E-Mail", value=email or "", key=f"u_mail_{uid}")
                    e_role = st.selectbox("Rolle", ["admin", "barlead", "user", "inventur"],
                                          index=["admin", "barlead", "user", "inventur"].index(role),
                                          key=f"u_role_{uid}")
                    new_pw = st.text_input("Neues Passwort (optional)", type="password", key=f"u_pw_{uid}")
                    s1, s2 = st.columns(2)
                    if s1.button("💾 Speichern", key=f"u_save_{uid}"):
                        try:
                            with conn() as cn:
                                c = cn.cursor()
                                c.execute(
                                    """UPDATE users
                                       SET first_name=?, last_name=?, email=?, role=?
                                       WHERE id=?""",
                                    (e_first, e_last, e_mail, e_role, uid)
                                )
                                cn.commit()
                            if new_pw:
                                ok = change_password(uname, new_pw)
                                st.success("Profil & Passwort gespeichert." if ok else "Profil gespeichert, Passwort fehlgeschlagen.")
                            else:
                                st.success("Gespeichert.")
                        except Exception as e:
                            st.error(f"Fehler: {e}")
                    if s2.button("🗑️ Löschen", key=f"u_del_{uid}"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("DELETE FROM users WHERE id=?", (uid,))
                            cn.commit()
                        st.warning(f"Benutzer '{uname}' gelöscht.")

    # ------------------- TAB 3: MITARBEITER -------------------
    with tabs[2]:
        section_title("🧍 Mitarbeiterverwaltung")
        with st.form("add_emp_form"):
            c1, c2, c3 = st.columns([2, 1, 1])
            ename = c1.text_input("Name")
            econtract = c2.selectbox("Vertragstyp", ["Teilzeit", "Vollzeit", "Geringfügig", "Fallweise"])
            ehourly = c3.number_input("Stundenlohn (€)", min_value=0.0, step=1.0, value=0.0)
            d1, d2 = st.columns([1, 1])
            ebarlead = d1.checkbox("Barleiter?")
            ebarno = d2.number_input("Bar-Nr. (1-7)", min_value=0, max_value=7, step=1, value=0)
            if st.form_submit_button("Mitarbeiter hinzufügen"):
                if not ename:
                    st.warning("Name erforderlich.")
                else:
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute(
                            """INSERT INTO employees(name, contract, hourly, is_barlead, bar_no)
                               VALUES(?,?,?,?,?)""",
                            (ename, econtract, ehourly, int(ebarlead), ebarno)
                        )
                        cn.commit()
                    st.success(f"✅ Mitarbeiter '{ename}' angelegt.")

        st.divider()
        with conn() as cn:
            c = cn.cursor()
            emps = c.execute("SELECT id, name, contract, hourly, is_barlead, bar_no FROM employees ORDER BY id").fetchall()
        if not emps:
            st.info("Noch keine Mitarbeiter.")
        else:
            for eid, name, contract, hourly, is_barlead, bar_no in emps:
                with st.expander(name):
                    a, b = st.columns(2)
                    e_name = a.text_input("Name", value=name, key=f"e_name_{eid}")
                    e_con = b.text_input("Vertragstyp", value=contract, key=f"e_con_{eid}")
                    c1, c2, c3 = st.columns([1, 1, 1])
                    e_hour = c1.number_input("Stundenlohn (€)", value=float(hourly or 0.0), key=f"e_hour_{eid}")
                    e_lead = c2.checkbox("Barleiter", value=bool(is_barlead), key=f"e_lead_{eid}")
                    e_bno = c3.number_input("Bar-Nr.", value=int(bar_no or 0), min_value=0, max_value=7, step=1, key=f"e_bno_{eid}")
                    s1, s2 = st.columns(2)
                    if s1.button("💾 Speichern", key=f"e_save_{eid}"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute(
                                """UPDATE employees
                                   SET name=?, contract=?, hourly=?, is_barlead=?, bar_no=?
                                   WHERE id=?""",
                                (e_name, e_con, float(e_hour), int(e_lead), int(e_bno), eid)
                            )
                            cn.commit()
                        st.success("Gespeichert.")
                    if s2.button("🗑️ Löschen", key=f"e_del_{eid}"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("DELETE FROM employees WHERE id=?", (eid,))
                            cn.commit()
                        st.warning(f"Mitarbeiter '{name}' gelöscht.")

    # ------------------- TAB 4: FIXKOSTEN -------------------
    with tabs[3]:
        section_title("💰 Monatliche Fixkosten")
        st.caption("Aktiv = wird im Forecast berücksichtigt.")
        with st.form("add_fixcost"):
            c1, c2 = st.columns([3, 1])
            fc_name = c1.text_input("Bezeichnung")
            fc_amount = c2.number_input("Betrag (€)", min_value=0.0, step=50.0, value=0.0)
            c3, c4 = st.columns([3, 1])
            fc_note = c3.text_input("Notiz (optional)")
            fc_active = c4.checkbox("Aktiv", value=True)
            if st.form_submit_button("➕ Fixkosten hinzufügen"):
                if not fc_name:
                    st.warning("Bezeichnung erforderlich.")
                else:
                    with conn() as cn:
                        c = cn.cursor()
                        c.execute(
                            """INSERT INTO fixcosts(name, amount, note, is_active)
                               VALUES(?,?,?,?)""",
                            (fc_name, float(fc_amount), fc_note, int(fc_active))
                        )
                        cn.commit()
                    st.success("Fixkosten hinzugefügt.")

        st.divider()
        with conn() as cn:
            c = cn.cursor()
            rows = c.execute(
                "SELECT id, name, amount, note, is_active FROM fixcosts ORDER BY is_active DESC, id"
            ).fetchall()
        if not rows:
            st.info("Noch keine Fixkosten erfasst.")
        else:
            for fid, name, amount, note, active in rows:
                with st.expander(f"{name} – {amount:.2f} € {'(aktiv)' if active else '(inaktiv)'}"):
                    a, b = st.columns([3, 1])
                    e_name = a.text_input("Bezeichnung", value=name, key=f"fc_name_{fid}")
                    e_amount = b.number_input("Betrag (€)", min_value=0.0, step=10.0, value=float(amount or 0.0), key=f"fc_amount_{fid}")
                    c1, c2 = st.columns([3, 1])
                    e_note = c1.text_input("Notiz", value=note or "", key=f"fc_note_{fid}")
                    e_active = c2.checkbox("Aktiv", value=bool(active), key=f"fc_active_{fid}")
                    s1, s2 = st.columns(2)
                    if s1.button("💾 Speichern", key=f"fc_save_{fid}"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute(
                                """UPDATE fixcosts SET name=?, amount=?, note=?, is_active=? WHERE id=?""",
                                (e_name, float(e_amount), e_note, int(e_active), fid)
                            )
                            cn.commit()
                        st.success("Gespeichert.")
                    if s2.button("🗑️ Löschen", key=f"fc_del_{fid}"):
                        with conn() as cn:
                            c = cn.cursor()
                            c.execute("DELETE FROM fixcosts WHERE id=?", (fid,))
                            cn.commit()
                        st.warning("Fixkosten entfernt.")

    # ------------------- TAB 5: DATENBANK -------------------
    with tabs[4]:
        section_title("🗂️ Datenbank – Übersicht & Export")
        table_order = [
            ("users", "👤 Benutzer"),
            ("employees", "🧍 Mitarbeiter"),
            ("daily", "📅 Tagesabrechnung"),
            ("kassen", "💵 Kassen"),
            ("garderobe", "🧥 Garderobe"),
            ("ausgaben", "🧾 Ausgaben"),
            ("inventur_items", "📦 Inventur-Artikel"),
            ("changelog", "📝 Changelog"),
            ("meta", "⚙️ Meta"),
        ]
        with conn() as cn:
            c = cn.cursor()
            existing = {n: _table_exists(c, n) for n, _ in table_order}
        display_tabs = [label for name, label in table_order if existing.get(name)]
        name_map = [name for name, label in table_order if existing.get(name)]
        if not display_tabs:
            st.info("Keine Tabellen gefunden.")
        else:
            subtabs = st.tabs(display_tabs)
            for i, sub in enumerate(subtabs):
                with sub:
                    tname = name_map[i]
                    with conn() as cn:
                        df = pd.read_sql(f"SELECT * FROM {tname}", cn)
                    st.dataframe(df, use_container_width=True, height=420)
                    csv = df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        "CSV exportieren",
                        csv,
                        file_name=f"{tname}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

    # ------------------- TAB 6: BACKUPS -------------------
    with tabs[5]:
        section_title("💾 Datenbank-Backups")
        col_a, col_b = st.columns([1, 1])
        if col_a.button("🧷 Backup jetzt erstellen", use_container_width=True):
            created = _create_backup()
            st.success(f"Backup erstellt: {created.name}")

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
            if col_b.button("🔄 Backup wiederherstellen", disabled=not ok, use_container_width=True):
                with st.spinner("Backup wird wiederhergestellt..."):
                    _restore_backup(chosen)
                    time.sleep(1.0)
                st.success("✅ Backup wiederhergestellt. Bitte App neu starten.")

    st.markdown("---")
    st.caption("© 2025 Roman Petek – Gastro Essentials Beta 1")
