import streamlit as st
from core.db import conn
from core.auth import _hash_password
import time

def render_setup():
    st.title("🔧 Erst-Setup · Gastro Essentials")

    # Fortschritt speichern
    step = st.session_state.get("setup_step", 1)

    # --------------------------------------------------------
    # STEP 1 – ADMIN ACCOUNT ANLEGEN
    # --------------------------------------------------------
    if step == 1:
        st.subheader("1️⃣ Admin-Benutzer anlegen")

        admin_user = st.text_input("Benutzername (Admin)", key="setup_admin_user")
        admin_pass = st.text_input("Passwort", type="password", key="setup_admin_pass")

        if st.button("✅ Admin anlegen", type="primary"):
            if not admin_user or not admin_pass:
                st.error("Bitte Benutzername UND Passwort eingeben.")
                return

            try:
                with conn() as c:
                    admin_user_clean = admin_user.strip()

                    # Prüfen ob bereits vorhanden
                    exists = c.execute(
                        "SELECT 1 FROM users WHERE username=?",
                        (admin_user_clean,)
                    ).fetchone()

                    pw_hash = _hash_password(admin_pass)

                    if exists:
                        # Update bestehender User
                        c.execute("""
                            UPDATE users
                            SET passhash=?, functions='admin', status='active'
                            WHERE username=?
                        """, (pw_hash, admin_user_clean))
                    else:
                        # Neuen Admin anlegen
                        c.execute("""
                            INSERT INTO users (username, passhash, functions, status)
                            VALUES (?, ?, 'admin', 'active')
                        """, (admin_user_clean, pw_hash))

                st.success("🎉 Admin erfolgreich angelegt!")
                st.session_state["setup_step"] = 2
                st.rerun()

            except Exception as e:
                st.error(f"❌ Fehler beim Erstellen des Admins: {e}")
                return

    # --------------------------------------------------------
    # STEP 2 – BETRIEBSPARAMETER
    # --------------------------------------------------------
    elif step == 2:
        st.subheader("2️⃣ Grundparameter des Betriebs")

        org_name = st.text_input("🧾 Name des Betriebs", key="setup_orgname")
        org_addr = st.text_area("📍 Adresse des Betriebs", key="setup_orgaddr")

        if st.button("✅ Setup abschließen", type="primary"):
            if not org_name:
                st.error("Bitte gib den Namen des Betriebs ein.")
                return

            try:
                with conn() as c:
                    c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES ('org_name', ?)", (org_name,))
                    c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES ('org_address', ?)", (org_addr or "",))
                    c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES ('setup_done', 'yes')")

                st.success("🎉 Setup erfolgreich abgeschlossen!")
                st.balloons()
                time.sleep(1.5)

                # Session zurücksetzen → führt beim nächsten Reload zum Login
                st.session_state.clear()
                st.rerun()

            except Exception as e:
                st.error(f"❌ Fehler beim Speichern der Daten: {e}")
                return
