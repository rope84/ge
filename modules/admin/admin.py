# modules/admin/admin.py
import streamlit as st
import pandas as pd
import shutil
import time
import datetime
from pathlib import Path

from core.db import BACKUP_DIR, DB_PATH, conn
from core.ui_theme import page_header, section_title
from core.config import APP_NAME, APP_VERSION
from core import auth
from core import auth as authmod
from modules import inventur_db as invdb

from .users_admin import render_users_admin


def render_admin():
    page_header("⚙️ Admin-Cockpit")
    tab1, tab2 = st.tabs(["🧩 Systemübersicht", "👤 Benutzerverwaltung"])

    with tab1:
        section_title("📊 Systemstatus")

        try:
            with conn() as c:
                orgname = c.execute("SELECT value FROM setup WHERE key='org_name'").fetchone()
                orgaddr = c.execute("SELECT value FROM setup WHERE key='org_address'").fetchone()
                user_count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                inventur_count = c.execute("SELECT COUNT(*) FROM inventur").fetchone()[0]
        except Exception as err:
            st.error(f"Fehler beim Laden der Systemdaten: {err}")
            return

        col1, col2 = st.columns(2)
        col1.metric("👥 Benutzer gesamt", user_count)
        col2.metric("📦 Inventur-Einträge", inventur_count)

        st.markdown("#### 🧾 Betriebsinformationen")
        st.text_input("Betriebsname", value=orgname[0] if orgname else "", disabled=True)
        st.text_area("Adresse", value=orgaddr[0] if orgaddr else "", disabled=True)

        st.markdown("#### 🔁 Datenbank & Version")
        st.caption(f"Version: {APP_NAME} {APP_VERSION}")
        if st.button("📦 Backup erstellen"):
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = BACKUP_DIR / f"gastro_backup_{timestamp}.db"
                shutil.copy(DB_PATH, backup_path)
                st.success(f"Backup erstellt: {backup_path.name}")
            except Exception as e:
                st.error(f"Backup fehlgeschlagen: {e}")

    with tab2:
        render_users_admin()
