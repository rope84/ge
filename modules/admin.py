import streamlit as st
import pandas as pd
import io
import shutil
import time
import datetime
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple

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
        "Datenbank-Backups: manuell, Statusanzeige",
        "Artikel-Import via Excel/CSV (Upsert)"
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

        # --- Basistabellen anlegen (falls nicht vorhanden) ---
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
            """,
        }
        for name, sql in tables_sql.items():
            c.execute(sql)

        # --- inventur_items: neu anlegen oder migrieren ---
        expected_cols = {
            "id": "INTEGER",
            "name": "TEXT",
            "unit_amount": "REAL",
            "unit": "TEXT",
            "purchase_price": "REAL",
            "stock_qty": "REAL",
            "last_updated": "TEXT",
        }

        if not _table_exists(c, "inventur_items"):
            # Frisch anlegen
            c.execute("""
                CREATE TABLE IF NOT EXISTS inventur_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    unit_amount REAL,
                    unit TEXT,
                    purchase_price REAL NOT NULL DEFAULT 0,
                    stock_qty REAL NOT NULL DEFAULT 0,
                    last_updated TEXT
                )
            """)
        else:
            # Migrieren: fehlende Spalten ergänzen
            cols = c.execute("PRAGMA table_info(inventur_items)").fetchall()
            existing = {row[1] for row in cols}  # row[1] = name
            # fehlende Spalten addieren
            if "name" not in existing:
                c.execute("ALTER TABLE inventur_items ADD COLUMN name TEXT")
            if "unit_amount" not in existing:
                c.execute("ALTER TABLE inventur_items ADD COLUMN unit_amount REAL")
            if "unit" not in existing:
                c.execute("ALTER TABLE inventur_items ADD COLUMN unit TEXT")
            if "purchase_price" not in existing:
                c.execute("ALTER TABLE inventur_items ADD COLUMN purchase_price REAL NOT NULL DEFAULT 0")
            if "stock_qty" not in existing:
                c.execute("ALTER TABLE inventur_items ADD COLUMN stock_qty REAL NOT NULL DEFAULT 0")
            if "last_updated" not in existing:
                c.execute("ALTER TABLE inventur_items ADD COLUMN last_updated TEXT")
            # Falls "name" NULL ist (durch ADD COLUMN), optional initial auffüllen:
            # (hier keine Zwangswerte setzen – Import/Editor übernimmt das)

        # --- optionale Hilfstabellen (falls genutzt) ---
        c.execute("""
            CREATE TABLE IF NOT EXISTS umsatz (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS inventur (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL
            )
        """)

        # --- Unique-Index für (name, unit_amount, unit) nur wenn Spalten vorhanden ---
        try:
            cols = c.execute("PRAGMA table_info(inventur_items)").fetchall()
            existing = {row[1] for row in cols}
            if {"name", "unit_amount", "unit"}.issubset(existing):
                c.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_inventur_items_unique
                    ON inventur_items(name, unit_amount, unit)
                """)
        except Exception:
            # Wenn das auf alten Schemas fehlschlägt, nicht hart abbrechen
            pass

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
        out: Dict[str, Optional[str]] = {}
        for k in keys:
            r = c.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
            out[k] = r[0] if r else None
        return out

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

def _db_table_stats() -> Tuple[int, int]:
    with conn() as cn:
        c = cn.cursor()
        tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        table_names = [t[0] for t in tables]
        total_rows = 0
        for t in table_names:
            try:
                total_rows += c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                pass
        return len(table_names), total_rows

# ---------------- UI Helpers ----------------
def _status_badge_from_days(days: Optional[int]) -> tuple[str, str, str]:
    if days is None:
        return ("#ef4444", "Kein Backup", "Es wurde noch kein Backup gefunden.")
    if days <= 5:
        return ("#22c55e", "Aktuell", f"Letztes Backup ist {days} Tag(e) alt.")
    if days <= 7:
        return ("#f59e0b", "Bald fällig", f"Letztes Backup ist {days} Tag(e) alt (empfohlen: ≤5 Tage).")
    return ("#ef4444", "Überfällig", f"Letztes Backup ist {days} Tag(e) alt (kritisch).")

def _card_html(title: str, color: str, lines: List[str]) -> str:
    body = "<br/>".join([f"<span style='opacity:0.85;font-size:12px;'>{ln}</span>" for ln in lines])
    return f"""
    <div style="
        display:flex; gap:12px; align-items:flex-start;
        padding:12px 14px; border-radius:14px;
        background:rgba(255,255,255,0.03);
        box-shadow: 0 6px 16px rgba(0,0,0,0.15);
        position:relative; overflow:hidden;
    ">
      <div style="
        position:absolute; left:0; top:0; bottom:0; width:6px;
        background: linear-gradient(180deg, {color}, {color}55);
        border-top-left-radius:14px; border-bottom-left-radius:14px;
      "></div>
      <div style="width:10px; height:10px; border-radius:50%; background:{color}; margin-top:4px;"></div>
      <div style="font-size:13px;">
        <b>{title}</b><br/>{body}
      </div>
    </div>
    """

def _role_badge(role: str) -> str:
    colors = {
        "admin": "#e11d48",
        "barlead": "#0ea5e9",
        "user": "#10b981",
        "inventur": "#f59e0b",
    }
    color = colors.get(role, "#6b7280")
    return f"<span style='background:{color}; color:white; padding:2px 6px; border-radius:999px; font-size:11px;'>{role}</span>"

def _pill(text: str, color: str = "#10b981") -> str:
    return f"<span style='background:{color}22; color:{color}; padding:2px 6px; border:1px solid {color}55; border-radius:999px; font-size:11px;'>{text}</span>"

# ---------- Parser: "Artikelname 0,2l" -> (name, 0.2, 'l')
_UNIT_RE = re.compile(r"\s*(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\s*$", re.IGNORECASE)

def _parse_article_name(raw: str) -> Tuple[str, Optional[float], Optional[str]]:
    if not raw:
        return ("", None, None)
    s = str(raw).strip()
    m = _UNIT_RE.search(s)
    if not m:
        return (s, None, None)
    amount_str = m.group(1).replace(",", ".")
    unit = m.group(2).lower()
    try:
        amount = float(amount_str)
    except Exception:
        amount = None
    name = _UNIT_RE.sub("", s).strip()
    return (name, amount, unit)

def _to_float(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

# ---------------- Übersicht ----------------
def _render_home():
    # Live-Zahlen
    users_cnt = _count_rows("users")
    emp_cnt   = _count_rows("employees")
    fix_cnt   = _count_rows("fixcosts")
    backups   = _list_backups()
    total_backups = len(backups)

    # Backup-Status
    last_bkp_dt = _last_backup_time()
    days_since = None if last_bkp_dt is None else (datetime.date.today() - last_bkp_dt.date()).days
    color_bkp, label_bkp, tip_bkp = _status_badge_from_days(days_since)

    # System-Gesamtstatus (grün wenn keine Issues)
    issues = []
    if users_cnt == 0:
        issues.append("Keine Benutzer angelegt.")
    if emp_cnt == 0:
        issues.append("Keine Mitarbeiter angelegt.")
    if color_bkp in ("#f59e0b", "#ef4444"):
        issues.append(tip_bkp)

    # Ampelfarbe für Systemstatus ableiten
    color_sys = "#22c55e" if not issues else ("#f59e0b" if any("empfohlen" in x for x in issues) else "#ef4444")
    today_str = datetime.date.today().strftime("%d.%m.%Y")

    # Datenbankstatus
    db_size = _db_size_mb()
    num_tables, total_rows = _db_table_stats()

    # --- obere Zeile: Systemstatus (links) + Backupstatus (rechts) ---
    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        html_sys = _small_status_card(
            "Systemstatus",
            color_sys,
            [
                f"Prüfung: {today_str}",
                f"Benutzer: {users_cnt}",
                f"Mitarbeiter: {emp_cnt}",
                f"Fixkosten: {fix_cnt}",
            ]
        )
        st.markdown(html_sys, unsafe_allow_html=True)

    with col_right:
        last_text = "—" if not last_bkp_dt else last_bkp_dt.strftime("%d.%m.%Y %H:%M")
        html_bkp = _small_status_card(
            "Backupstatus",
            color_bkp,
            [
                f"Status: {label_bkp}",
                f"Info: {tip_bkp}",
                f"Letztes Backup: {last_text}",
                f"Backups gesamt: {total_backups}",
            ]
        )
        st.markdown(html_bkp, unsafe_allow_html=True)

    # Details nur bei Warnungen/Fehlern anzeigen – rechts als Expander
    if issues:
        with st.expander("🔍 Systemhinweise öffnen", expanded=False):
            for issue in issues:
                st.markdown(f"- {issue}")
    else:
        st.caption("🟢 Keine Systemhinweise")

    st.divider()

    # --- Datenbankstatus im gleichen Stil wie oben ---
    section_title("🗂️ Datenbankstatus")
    color_db = "#22c55e"  # neutral grün (keine Ampellogik nötig)
    html_db = _small_status_card(
        "Datenbank",
        color_db,
        [
            f"📦 Dateigröße: {db_size} MB",
            f"🧩 Tabellen: {num_tables}",
            f"🔢 Gesamtzeilen: {total_rows}",
            f"💾 Backups gesamt: {total_backups}",
        ]
    )
    st.markdown(html_db, unsafe_allow_html=True)

    st.divider()

    # --- Changelog klein & aktuell ---
    section_title("📝 Änderungsprotokoll")
    with conn() as cn:
        df = pd.read_sql(
            "SELECT created_at, version, note FROM changelog "
            "ORDER BY datetime(created_at) DESC LIMIT 20",
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
        "business_capacity",   # neu: Fassungsvermögen (Personen)
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
        capacity = h.number_input("Fassungsvermögen (Personen)", min_value=0, step=10,
                                  value=int(values.get("business_capacity") or 0))
        note = st.text_input("Notiz (optional)", value=values.get("business_note") or "")

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
                "business_capacity": str(capacity),
                "business_note": note,
            })
            st.success("Betriebsdaten gespeichert.")

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
            with st.expander(f"{uname}", expanded=False):
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
                st.markdown(
                    _pill("aktiv", "#10b981") if active else _pill("inaktiv", "#6b7280"),
                    unsafe_allow_html=True
                )
                st.write("")

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

# ---------------- Datenbank – Übersicht & Import ----------------
def _render_db_overview():
    section_title("🗂️ Datenbank")

    # zwei Sub-Tabs: Übersicht & Export | Artikel-Import
    subtab_overview, subtab_import = st.tabs(["📄 Tabellen ansehen & exportieren", "📦 Artikel-Import (Excel/CSV)"])

    # --- Subtab 1: Tabellen ansehen/exportieren ---
    with subtab_overview:
        with conn() as cn:
            c = cn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
            tables = [r[0] for r in c.fetchall()]

        if not tables:
            st.info("Keine Tabellen vorhanden.")
        else:
            # kleine, hübschere Auswahl: Label + Kurzbeschreibung + Zeilenzahl
            friendly = {
                "users": "👤 users – Benutzer",
                "employees": "🧍 employees – Mitarbeiter",
                "fixcosts": "💰 fixcosts – Fixkosten",
                "meta": "⚙️ meta – Metadaten",
                "changelog": "📝 changelog – Änderungen",
                "inventur_items": "📦 inventur_items – Artikel (Inventur)",
                "umsatz": "📈 umsatz – Umsätze (optional)",
                "inventur": "🗓️ inventur – Inventur-Läufe"
            }
            # baue Liste mit Rowcounts
            rows_map: Dict[str, int] = {}
            with conn() as cn:
                c = cn.cursor()
                for t in tables:
                    try:
                        rows_map[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    except Exception:
                        rows_map[t] = 0

            labels = []
            for t in tables:
                label = friendly.get(t, t)
                labels.append(f"{label}  ·  {rows_map[t]} Zeilen")

            idx = st.selectbox("Tabelle auswählen", options=list(range(len(tables))),
                               format_func=lambda i: labels[i])

            if idx is not None:
                tname = tables[idx]
                with conn() as cn:
                    df = pd.read_sql(f"SELECT * FROM {tname}", cn)
                st.dataframe(df, use_container_width=True, height=420)
                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button("📤 CSV exportieren", csv, file_name=f"{tname}.csv", mime="text/csv")

    # --- Subtab 2: Artikel-Import ---
    with subtab_import:
        st.markdown("Lade eine Excel- oder CSV-Datei hoch. Erwartetes Format:")
        st.markdown("- **Spalte A**: Artikelname (optional mit Menge/Einheit, z. B. `Coca Cola 0,2l`, `Vodka 2cl`, `Red Bull 250 ml`)")
        st.markdown("- **Spalte B**: Bestand (Zahl)")
        st.markdown("- **Spalte C**: Netto-Einkaufspreis (Zahl, Komma oder Punkt erlaubt)")
        st.caption("Spalte D (Summe) wird ignoriert – berechnen wir selbst.")

        # Template anbieten
        sample = pd.DataFrame({
            "Artikel (Name + optional Menge)": ["Coca Cola 0,2l", "Vodka 2cl", "Red Bull 250 ml"],
            "Bestand": [120, 80, 60],
            "Einkaufspreis Netto": ["0,48", "0,22", "0,85"],
            "Summe (optional)": [None, None, None]
        })
        csv_bytes = sample.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 CSV-Template herunterladen", data=csv_bytes, file_name="artikel_template.csv", mime="text/csv")

        file = st.file_uploader("Datei hochladen", type=["xlsx", "xls", "csv"])
        if file:
            # Einlesen
            try:
                if file.name.lower().endswith(".csv"):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
            except Exception as e:
                st.error(f"Datei konnte nicht gelesen werden: {e}")
                return

            # Minimal-Validierung
            if df.shape[1] < 3:
                st.error("Mindestens 3 Spalten erforderlich (A=Artikel, B=Bestand, C=EK).")
                return

            # Spalten greifen
            col_name = df.columns[0]
            col_qty  = df.columns[1]
            col_ek   = df.columns[2]

            # Normalisieren
            preview_rows = []
            for _, row in df.iterrows():
                raw_name = str(row.get(col_name, "")).strip()
                if not raw_name:
                    continue
                name, u_amount, unit = _parse_article_name(raw_name)
                qty = _to_float(row.get(col_qty))
                ek  = _to_float(row.get(col_ek))
                preview_rows.append({
                    "name": name,
                    "unit_amount": u_amount,
                    "unit": unit,
                    "stock_qty": qty,
                    "purchase_price": ek,
                    "inventur_summe": round(qty * ek, 2)
                })

            if not preview_rows:
                st.warning("Keine gültigen Zeilen gefunden.")
                return

            st.subheader("Vorschau")
            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)

            if st.button("✅ Import starten (Upsert)"):
                inserted, updated = 0, 0
                now = datetime.datetime.now().isoformat(timespec="seconds")
                with conn() as cn:
                    c = cn.cursor()
                    for r in preview_rows:
                        # versuche Update via UNIQUE-Key, falls nicht vorhanden -> Insert
                        # 1) Update
                        res = c.execute("""
                            UPDATE inventur_items
                               SET stock_qty=?,
                                   purchase_price=?,
                                   last_updated=?
                             WHERE name=? AND
                                   (unit_amount IS ? OR unit_amount=?) AND
                                   (unit IS ? OR unit=?)
                        """, (
                            r["stock_qty"], r["purchase_price"], now,
                            r["name"], r["unit_amount"], r["unit_amount"],
                            r["unit"], r["unit"]
                        ))
                        if res.rowcount and res.rowcount > 0:
                            updated += 1
                            continue
                        # 2) Insert
                        c.execute("""
                            INSERT INTO inventur_items(name, unit_amount, unit, purchase_price, stock_qty, last_updated)
                            VALUES(?,?,?,?,?,?)
                        """, (r["name"], r["unit_amount"], r["unit"], r["purchase_price"], r["stock_qty"], now))
                        inserted += 1
                    cn.commit()
                st.success(f"Import fertig: {inserted} neu, {updated} aktualisiert.")

# ---------------- Backup-Verwaltung ----------------
def _render_backup_admin():
    section_title("💾 Datenbank-Backups")

    lb = _last_backup_time()
    last_text = lb.strftime("%d.%m.%Y %H:%M") if lb else "—"
    st.caption(f"Letztes Backup: **{last_text}**")

    col_a, col_b = st.columns([1, 1])
    if col_a.button("🧷 Backup jetzt erstellen", key="bkp_create_admin", use_container_width=True):
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

    ok = st.checkbox("Ich bestätige die Wiederherstellung dieses Backups.", key="bkp_restore_confirm")
    if col_b.button("🔄 Backup wiederherstellen", key="bkp_restore_action", disabled=not ok, use_container_width=True):
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
    with tabs[2]:
        _render_user_admin()
    with tabs[3]:
        _render_employee_admin()
    with tabs[4]:
        _render_db_overview()
    with tabs[5]:
        _render_backup_admin()

    st.markdown("---")
    st.caption(f"© 2025 Roman Petek – {APP_NAME} {APP_VERSION}")
