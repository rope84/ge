import streamlit as st
from core.db import conn
from core.auth import _hash_password

def render_setup():
    st.title("🔧 Erst-Setup: Gastro Essentials")

    step = st.session_state.get("setup_step", 1)

    if step == 1:
        st.subheader("1️⃣ Admin-Benutzer anlegen")
        admin_user = st.text_input("Benutzername (Admin)", key="setup_admin_user")
        admin_pass = st.text_input("Passwort", type="password", key="setup_admin_pass")
        if st.button("✅ Admin anlegen"):
            if admin_user and admin_pass:
                try:
                    with conn() as c:
                        c.execute("""
                            INSERT OR IGNORE INTO users (username, passhash, role, status)
                            VALUES (?, ?, 'admin', 'active')
                        """, (admin_user, _hash_password(admin_pass)))
                    st.session_state["setup_step"] = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"Fehler beim Erstellen des Admins: {e}")
            else:
                st.error("Bitte Benutzername und Passwort eingeben.")

    elif step == 2:
        st.subheader("2️⃣ Grundparameter des Betriebs")
        name = st.text_input("🧾 Name des Betriebs", key="setup_orgname")
        adresse = st.text_area("📍 Adresse", key="setup_orgaddr")

        if st.button("✅ Setup abschließen"):
            if name:
                try:
                    with conn() as c:
                        c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES (?, ?)", ("org_name", name))
                        c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES (?, ?)", ("org_address", adresse or ""))
                        c.execute("INSERT OR REPLACE INTO setup (key, value) VALUES (?, ?)", ("setup_done", "yes"))
                    st.success("Setup abgeschlossen 🎉")
                    st.balloons()
                    st.switch_page("app.py")  # Optionaler Refresh
                except Exception as e:
                    st.error(f"Fehler beim Abschließen des Setups: {e}")
            else:
                st.error("Name des Betriebs ist erforderlich.")
