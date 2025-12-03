import streamlit as st
from core.db import conn
from core.auth import _hash_password
import time

def render_setup():
    st.title("🔧 Erst-Setup: Gastro Essentials")

    step = st.session_state.get("setup_step", 1)

    # -----------------------------------
    # STEP 1 — ADMIN USER ANLEGEN
    # -----------------------------------
    if step == 1:
        st.subheader("1️⃣ Admin-Benutzer anlegen")

        admin_user = st.text_input("Benutzername (Admin)", key="setup_admin_user")
        admin_pass = st.text_input("Passwort", type="password", key="setup_admin_pass")

        if st.button("✅ Admin anlegen"):
            if not admin_user or not admin_pass:
                st.error("Bitte Benutzername UND Passwort eingeben.")
                return

            try:
                with conn() as c:
                    # Existenz prüfen, um Fehler bei REPLACE zu vermeiden
                    exists = c.execute("SELECT 1 FROM users WHERE username = ?", (admin_user.strip(),)).fetchone()
                    if exists:
                        c.execute("UPDATE users SET passhash=?, functions='admin', status='active' WHERE username=?",
                                  (_hash_password(admin_pass), admin_user.strip()))
                    else:
                        c.execute("""
                            INSERT INTO users (username, passhash, functions, status)
                            VALUES (?, ?, 'admin', 'active')
                        """, (admin_user.strip(), _hash_password(admin_pass)))

                st.success("Admin erfolgreich angelegt! 🎉")
                st.session_state["setup_step"] = 2
                st.rerun()

            except Exception as e:
                st.error(f"Fehler beim Erstellen des Admins: {e}")
                return

    # -----------------------------------
    # STEP 2 — BETRIEBSPARAMETER
    # -----------------------------------
    elif step == 2:
        st.subheader("2️⃣ Grundparameter des Betriebs")

        orgname = st.text_input("🧾 Name des Betriebs", key="setup_orgname")
        orgaddr = st.text_area("📍 Adresse", key="setup_orgaddr")

        if st.button("✅ Setup abschließen"):
            if not orgname:
                st.error("Bitte den Namen des Betriebs eingeben.")
                return

            try:
                with conn() as c:
                    c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES (?, ?)", ("org_name", orgname))
                    c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES (?, ?)", ("org_address", orgaddr or ""))
                    c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES (?, ?)", ("setup_done", "yes"))

                st.success("🎉 Setup erfolgreich abgeschlossen!")
                st.balloons()
                time.sleep(2)
                st.session_state.clear()
                st.rerun()

            except Exception as e:
                st.error(f"Fehler beim Abschließen des Setups: {e}")
                return
