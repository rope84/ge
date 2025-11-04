import streamlit as st
import pandas as pd
import shutil
import time
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from core.db import BACKUP_DIR, DB_PATH, conn
from core.ui_theme import page_header, section_title
from core.config import APP_NAME, APP_VERSION
from .users_admin import render_users_admin


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

# ---------------- Hilfsfunktionen ----------------
def _table_exists(c, name: str) -> bool:
    return c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS changelog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                version TEXT NOT NULL,
                note TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS fixcosts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                note TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cn.commit()


def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None


def _set_meta_many(data: Dict[str, str]):
    with conn() as cn:
        c = cn.cursor()
        for k, v in data.items():
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (k, v))
        cn.commit()


# ---------------- UI Helpers ----------------
def _card_html(title: str, color: str, lines: List[str]) -> str:
    body = "<br/>".join([f"<span style='opacity:0.85;font-size:12px;'>{ln}</span>" for ln in lines])
    return f"""
    <div style="
        display:flex; gap:12px; align-items:flex-start;
        padding:12px 14px; border-radius:14px;
        background:rgba(255,255,255,0.03);
        box-shadow:0 6px 16px rgba(0,0,0,0.15);
        position:relative; overflow:hidden;
    ">
      <div style="width:10px; height:10px; border-radius:50%; background:{color}; margin-top:4px;"></div>
      <div style="font-size:13px;">
        <b>{title}</b><br/>{body}
      </div>
    </div>
    """

# ---------------- Haupt-Render ----------------
def render_admin():
    """Entry-Point für das Admin-Cockpit."""
    if st.session_state.get("role") != "admin":
        st.error("Kein Zugriff. Adminrechte erforderlich.")
        return

    with st.spinner("🔄 Admin-Cockpit wird geladen..."):
        _ensure_tables()
        page_header("Admin-Cockpit", "System- und Datenübersicht")

        tabs = st.tabs([
            "🏠 Übersicht",
            "👤 Benutzer",
            "💰 Fixkosten",
            "🗂️ Datenbank",
            "💾 Backups"
        ])

        with tabs[0]:
            st.subheader("Systemübersicht")
            st.write("Hier werden Kennzahlen und Changelog angezeigt (Platzhalter).")

        with tabs[1]:
            render_users_admin()

        with tabs[2]:
            st.subheader("Fixkostenverwaltung (Platzhalter)")

        with tabs[3]:
            st.subheader("Datenbank-Übersicht (Platzhalter)")

        with tabs[4]:
            st.subheader("Backup-Verwaltung (Platzhalter)")

    st.markdown("---")
    st.caption(f"© 2025 Roman Petek – {APP_NAME} {APP_VERSION}")
