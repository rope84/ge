import re
import streamlit as st

from core.ui_theme import page_header, section_title
from core.auth import change_password
from core.db import conn
from core.config import APP_NAME, APP_VERSION


# -------------------------------
# DB-Helpers
# -------------------------------
def _fetch_user(username: str):
    with conn() as cn:
        c = cn.cursor()
        return c.execute("""
            SELECT id, username, first_name, last_name, email, role
            FROM users
            WHERE username = ?
            LIMIT 1
        """, (username.strip(),)).fetchone()


def _update_user_profile(old_username: str, new_username: str, first_name: str, last_name: str, email: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            UPDATE users
            SET username=?, first_name=?, last_name=?, email=?
            WHERE username=?
        """, (new_username.strip(), first_name.strip(), last_name.strip(), email.strip(), old_username))
        cn.commit()


# -------------------------------
# Passwort-Policy
# -------------------------------
_PW_HINT = "Mind. 6–8 Zeichen, mindestens 1 Zahl und 1 Sonderzeichen."


def _valid_password(pw: str) -> bool:
    if not 6 <= len(pw) <= 8:
        return False
    if not re.search(r"\d", pw):
        return False
    if not re.search(r"[^A-Za-z0-9]", pw):
        return False
    return True


# -------------------------------
# Render
# -------------------------------
def render_profile(username: str):
    page_header("👤 Profil", "Deine Daten & Zugang verwalten")

    row = _fetch_user(username)
    if not row:
        st.error("Benutzer konnte nicht geladen werden.")
        return

    uid, uname, first_name, last_name, email, role = row
    scope = st.session_state.get("scope", "-")

    st.info(f"🛡️ Rolle: **{role}**  |  🧭 Rechte: **{scope or '–'}**")

    tabs = st.tabs(["🪪 Profil", "🔐 Passwort ändern"])

    # ------------------ TAB: PROFIL ------------------
    with tabs[0]:
        section_title("Persönliche Daten")

        if st.checkbox("Ich möchte meinen Benutzernamen ändern"):
            new_username = st.text_input("Benutzername", value=uname)
        else:
            new_username = uname
            st.text_input("Benutzername", value=uname, disabled=True)

        col1, col2 = st.columns(2)
        new_first = col1.text_input("Vorname", value=first_name or "", placeholder="z. B. Roman")
        new_last = col2.text_input("Nachname", value=last_name or "", placeholder="z. B. Petek")
        new_email = st.text_input("E-Mail-Adresse", value=email or "", placeholder="z. B. roman@example.com")

        if st.button("💾 Änderungen speichern", use_container_width=True, key="btn_profile_save"):
            _update_user_profile(uname, new_username, new_first, new_last, new_email)
            st.success("Profil erfolgreich aktualisiert!")
            if new_username != uname:
                st.warning("🔁 Der Benutzername wurde geändert. Bitte neu anmelden.")
                st.session_state.clear()

    # ------------------ TAB: PASSWORT ------------------
    with tabs[1]:
        section_title("Passwort ändern")

        st.caption(_PW_HINT)
        old_pw = st.text_input("Aktuelles Passwort", type="password")
        new_pw = st.text_input("Neues Passwort", type="password", help=_PW_HINT)
        confirm_pw = st.text_input("Neues Passwort bestätigen", type="password")

        with st.expander("Passwort-Anforderungen anzeigen", expanded=False):
            st.markdown(
                "- **Länge:** 6–8 Zeichen\n"
                "- **Mindestens eine Zahl** (0–9)\n"
                "- **Mindestens ein Sonderzeichen** (z. B. !, ?, %, _)"
            )

        if st.button("Passwort aktualisieren", use_container_width=True, key="btn_pw_change"):
            if new_pw != confirm_pw:
                st.error("❌ Die neuen Passwörter stimmen nicht überein.")
            elif not _valid_password(new_pw):
                st.error(f"❌ Passwort erfüllt die Anforderungen nicht. {_PW_HINT}")
            else:
                ok, msg = change_password(username, old_pw, new_pw)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    st.markdown("---")
    st.caption(f"© 2025 Roman Petek – {APP_NAME} {APP_VERSION}")
