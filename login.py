# login.py
import streamlit as st
from typing import Tuple
import importlib
from core.db import conn
from core.config import APP_NAME, APP_VERSION


# ----------------------------------------------------------
# Lazy-Loader für core.auth (verhindert Circular Imports)
# ----------------------------------------------------------
def _lazy_auth():
    try:
        from core import auth as _a
        return _a
    except Exception:
        return importlib.import_module("core.auth")


# ----------------------------------------------------------
# Betriebsname aus meta holen
# ----------------------------------------------------------
def _get_business_name() -> str:
    try:
        with conn() as cn:
            c = cn.cursor()
            row = c.execute(
                "SELECT value FROM meta WHERE key='business_name'"
            ).fetchone()
        if row and (row[0] or "").strip():
            return row[0].strip()
    except Exception:
        pass
    return "Gastro Essentials"


# ----------------------------------------------------------
# LOGIN-FORMULAR
# ----------------------------------------------------------
def render_login_form(app_name: str, app_version: str) -> Tuple[str, str, bool]:
    """
    Zeichnet das Login-UI.
    Rückgabe: (username, password, pressed_login)
    """

    club_name = _get_business_name()

    # ------------------------------------------------------
    # GLOBAL STYLES (Zentriert, Glass, Pille killen)
    # ------------------------------------------------------
    st.markdown(
        f"""
        <style>
        /* Sidebar ausblenden */
        [data-testid="stSidebar"] {{
            display: none !important;
        }}

        body {{
            background: radial-gradient(900px 500px at 20% -10%, #1e1b4b33, transparent),
                        radial-gradient(900px 500px at 120% 0%, #0f766e33, transparent),
                        #020617;
        }}

        /* Hauptcontainer zentrieren */
        [data-testid="block-container"] {{
            max-width: 900px !important;
            margin: 0 auto !important;
            padding-top: 10vh !important;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}

        /* Überschrift zentriert */
        .ge-title {{
            font-size: 1.9rem;
            font-weight: 700;
            color: #f9fafb;
            margin-bottom: 4px;
            text-align: center;
        }}
        .ge-sub {{
            font-size: .95rem;
            opacity: .8;
            text-align: center;
            margin-bottom: 4px;
            color: #e5e7eb;
        }}
        .ge-mini {{
            font-size: .8rem;
            opacity: .55;
            text-align: center;
            margin-bottom: 22px;
        }}

        /* PILLE / Hero-Balken sicher killen */
        div[style*="linear-gradient"][style*="999px"],
        div[style*="linear-gradient"][style*="border-radius: 999px"],
        div[style*="linear-gradient"][style*="border-radius:999px"] {{
            display: none !important;
        }}

        /* ÄUSSEREN Form-Rahmen komplett entfernen */
        [data-testid="stForm"] {{
            max-width: 520px;
            margin: 0 auto 22px auto !important;
            padding: 0 !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        /* Blaue Glass-Card innerhalb des Forms */
        [data-testid="stForm"] > div:first-child {{
            background: linear-gradient(135deg, rgba(15,23,42,0.96), rgba(37,99,235,0.88)) !important;
            border-radius: 24px !important;
            padding: 26px 26px 22px 26px !important;
            border: none !important;
            box-shadow:
                0 24px 55px rgba(0,0,0,0.65),
                0 0 0 1px rgba(255,255,255,0.04) !important;
            margin: 0 !important;
        }}

        /* Expander-Header etwas hübscher */
        .streamlit-expanderHeader {{
            font-size: 0.95rem !important;
            color: #e5e7eb !important;
        }}
        .streamlit-expanderHeader:hover {{
            color: #ffffff !important;
        }}

        /* Footer */
        .ge-footer {{
            text-align: center;
            opacity: .65;
            font-size: .8rem;
            margin-top: 18px;
        }}

        /* Streamlit-Toolbar + Badges ausblenden */
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stCloudAppStatus"],
        header [data-testid="stToolbar"],
        header [data-testid="stHeaderActionButtons"],
        header [data-testid="stActionButton"],
        .stDeployButton,
        .viewerBadge_container__r3R7,
        button[title="Manage app"],
        button[title="View source"] {{
            display: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------
    # HEADER (Clubname + Unterzeilen)
    # ------------------------------------------------------
    st.markdown(
        f"""
        <div class="ge-title">{club_name}</div>
        <div class="ge-sub">Bitte melde dich an, um fortzufahren.</div>
        <div class="ge-mini">{APP_NAME} · v{app_version}</div>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------
    # LOGIN FORM (Glass-Card durch CSS)
    # ------------------------------------------------------
    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input("Benutzername", placeholder="username", key="ge_user")

        password = st.text_input(
            "Passwort",
            type="password",
            placeholder="••••••••",
            key="ge_pass",
        )
        show_pw = st.checkbox("Passwort anzeigen", key="ge_showpw")

        if show_pw:
            st.info("Passwort-Anzeige aktiviert.")
            st.text_input("Passwort (sichtbar)", value=password, type="default", key="ge_pw_visible")

        st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
        pressed_login = st.form_submit_button("Einloggen", use_container_width=True)

    # ------------------------------------------------------
    # REGISTRIERUNG (gleiche Glass-Optik, eigenes Form)
    # ------------------------------------------------------
    with st.expander("Noch kein Konto? Jetzt registrieren", expanded=False):
        with st.form("ge_register_form", clear_on_submit=True):
            r_user = st.text_input("Benutzername", key="reg_user")
            r_fn   = st.text_input("Vorname", key="reg_fn")
            r_ln   = st.text_input("Nachname", key="reg_ln")
            r_mail = st.text_input("E-Mail", key="reg_mail")
            r_pw   = st.text_input("Passwort", type="password", key="reg_pw")
            r_pw2  = st.text_input("Passwort wiederholen", type="password", key="reg_pw2")

            submit_reg = st.form_submit_button("Registrierung absenden", use_container_width=True)

        if submit_reg:
            if r_pw != r_pw2:
                st.error("Passwörter stimmen nicht überein.")
            else:
                try:
                    auth = _lazy_auth()
                    ok, msg = auth.register_user(r_user, r_fn, r_ln, r_mail, r_pw)
                    if ok:
                        st.success(msg)
                        st.info("Sobald ein Admin dich freigibt, ist der Login möglich.")
                    else:
                        st.error(msg)
                except Exception as e:
                    st.error("Registrierung fehlgeschlagen (interner Fehler).")
                    st.exception(e)

    # ------------------------------------------------------
    # FOOTER
    # ------------------------------------------------------
    st.markdown(
        "<div class='ge-footer'>© Gastro Essentials</div>",
        unsafe_allow_html=True,
    )

    return (username or "").strip(), (password or ""), bool(pressed_login)
