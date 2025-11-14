# login.py
import streamlit as st
from typing import Tuple
import importlib


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
# LOGIN-FORMULAR MIT GLASS CARD DESIGN
# ----------------------------------------------------------
def render_login_form(app_name: str, app_version: str) -> Tuple[str, str, bool]:
    """
    Gibt zurück: (username, password, pressed_login)
    Registrierung wird separat verarbeitet.
    """

    # ------------------------------------------------------
    # GLOBAL STYLE: CENTER, GLASS, REMOVE PILLE
    # ------------------------------------------------------
    st.markdown(
        f"""
        <style>
        [data-testid="stSidebar"] {{ display:none !important; }}

        body {{
            background: radial-gradient(900px 500px at 20% -10%, #1e1b4b33, transparent),
                        radial-gradient(900px 500px at 120% 0%, #0f766e33, transparent),
                        #020617;
        }}

        /* Hauptbereich zentrieren */
        [data-testid="block-container"] {{
            max-width: 900px !important;
            margin: 0 auto !important;
            padding-top: 8vh !important;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}

        /* Entfernt die frühere „Pille“ (Header-Gradient-Balken) */
        div[style*="border-radius: 999px"][style*="linear-gradient"],
        div[style*="border-radius:999px"][style*="linear-gradient"] {{
            display:none !important;
        }}

        /* Blue Glass Card */
        .ge-card {{
            max-width: 520px;
            margin: 0 auto 26px auto;
            padding: 28px;
            border-radius: 24px;
            background: linear-gradient(
                135deg,
                rgba(15,23,42,0.96),
                rgba(30,64,175,0.88)
            );
            backdrop-filter: blur(18px);
            box-shadow:
                0 24px 55px rgba(0,0,0,0.6),
                0 0 0 1px rgba(255,255,255,0.04);
            border: none !important;
        }}

        /* Entfernt weißen Rand um das Form-Element */
        div[data-testid="stForm"] > div:first-child {{
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            box-shadow: none !important;
        }}

        /* Expander Style */
        .streamlit-expanderHeader {{
            font-size: 0.95rem !important;
            color: #cbd5e1 !important;
        }}
        .streamlit-expanderHeader:hover {{
            color: white !important;
        }}

        .ge-footer {{
            text-align:center;
            opacity:.65;
            font-size:.8rem;
            margin-top: 20px;
        }}

        /* Toolbar & Badges ausblenden */
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stCloudAppStatus"],
        header [data-testid="stToolbar"],
        header [data-testid="stHeaderActionButtons"],
        header [data-testid="stActionButton"],
        .stDeployButton,
        .viewerBadge_container__r3R7,
        button[title="Manage app"],
        button[title="View source"],
        [data-testid="baseButton-secondary"]:has(> div:empty)
        {{ display:none !important; }}

        </style>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------
    # TITELBEREICH MIT CLUB-NAMEN (aus Admin-Einstellungen)
    # ------------------------------------------------------
    club_name = "Gastro Essentials"
    try:
        meta = st.session_state.get("club_meta", {})
        if meta and meta.get("club_name"):
            club_name = meta["club_name"]
    except Exception:
        pass

    st.markdown(
        f"""
        <div style='text-align:center; margin-bottom:22px;'>
            <div style="font-size:1.9rem; font-weight:700; color:white;">
                {club_name}
            </div>
            <div style="opacity:.75; margin-top:4px;">
                Bitte melde dich an, um fortzufahren.
            </div>
            <div style="opacity:.45; font-size:.85rem; margin-top:6px;">
                Gastro Essentials · v{app_version}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------
    # LOGIN-CARD
    # ------------------------------------------------------
    st.markdown("<div class='ge-card'>", unsafe_allow_html=True)

    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input("Benutzername", placeholder="username", key="ge_user")

        password = st.text_input("Passwort", type="password", placeholder="••••••••", key="ge_pass")
        show_pw  = st.checkbox("Passwort anzeigen", key="ge_showpw")

        if show_pw:
            st.info("Passwort-Anzeige aktiviert.")
            st.text_input("Passwort (sichtbar)", value=password, type="default", key="pw_visible")

        st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")

        pressed_login = st.form_submit_button("Einloggen", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ------------------------------------------------------
    # REGISTRIERUNG – gleiche Glass-Card
    # ------------------------------------------------------
    with st.expander("Noch kein Konto? Jetzt registrieren", expanded=False):
        st.markdown("<div class='ge-card'>", unsafe_allow_html=True)

        with st.form("ge_register_form", clear_on_submit=True):
            r_user = st.text_input("Benutzername", key="reg_user")
            r_fn   = st.text_input("Vorname", key="reg_fn")
            r_ln   = st.text_input("Nachname", key="reg_ln")
            r_mail = st.text_input("E-Mail", key="reg_mail")

            r_pw   = st.text_input("Passwort", type="password", key="reg_pw")
            r_pw2  = st.text_input("Passwort wiederholen", type="password", key="reg_pw2")

            submit_reg = st.form_submit_button("Registrierung absenden", use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

        if submit_reg:
            if r_pw != r_pw2:
                st.error("Passwörter stimmen nicht überein.")
            else:
                try:
                    auth = _lazy_auth()
                    ok, msg = auth.register_user(r_user, r_fn, r_ln, r_mail, r_pw)
                    if ok:
                        st.success(msg)
                        st.info("Ein Admin muss deine Registrierung freigeben.")
                    else:
                        st.error(msg)
                except Exception as e:
                    st.error("Registrierung fehlgeschlagen.")
                    st.exception(e)

    # ------------------------------------------------------
    # FOOTER
    # ------------------------------------------------------
    st.markdown(
        "<div class='ge-footer'>© O-der Klub · Gastro Essentials</div>",
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------
    # Rückgabe
    # ------------------------------------------------------
    return (username or "").strip(), (password or ""), bool(pressed_login)
