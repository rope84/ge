# profile.py
import re
import streamlit as st
from core.ui_theme import page_header, section_title
from core.auth import change_password
from core.db import conn


# -------------------------------
# DB-Helpers
# -------------------------------
def _fetch_user(username: str):
    """Lädt Benutzerdaten aus der DB."""
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("""
            SELECT id, username, first_name, last_name, email, role
            FROM users
            WHERE username = ?
            LIMIT 1
        """, (username.strip(),)).fetchone()
    return row


def _update_user_profile(username: str, first_name: str, last_name: str, email: str):
    """Aktualisiert Profilinformationen (Name, E-Mail)."""
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            UPDATE users
            SET first_name=?, last_name=?, email=?
            WHERE username=?
        """, (first_name.strip(), last_name.strip(), email.strip(), username))
        cn.commit()


# -------------------------------
# Passwort-Policy (6–8, Zahl + Sonderzeichen)
# -------------------------------
_PW_HINT = "Mind. 6–8 Zeichen, mindestens 1 Zahl und 1 Sonderzeichen."

def _valid_password(pw: str) -> bool:
    """Einfache Policy-Prüfung."""
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

    # Tabs: Profil | Passwort ändern
    tabs = st.tabs(["🪪 Profil", "🔐 Passwort ändern"])

    # ------------------ TAB: PROFIL ------------------
    with tabs[0]:
        section_title("Persönliche Daten")

        col1, col2 = st.columns(2)
        new_first = col1.text_input("Vorname", value=first_name or "", placeholder="z. B. Roman")
        new_last = col2.text_input("Nachname", value=last_name or "", placeholder="z. B. Petek")
        new_email = st.text_input("E-Mail-Adresse", value=email or "", placeholder="z. B. roman@example.com")

        if st.button("💾 Änderungen speichern", use_container_width=True, key="btn_profile_save"):
            _update_user_profile(username, new_first, new_last, new_email)
            st.success("Profil erfolgreich aktualisiert!")

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
                "- **Mindestens ein Sonderzeichen** (z. B. !, ?, %, _)\n"
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
    st.caption("© 2025 Roman Petek – Gastro Essentials")
