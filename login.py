# login.py
import streamlit as st
from typing import Tuple
import importlib


def _lazy_auth():
    """Lädt core.auth nur bei Bedarf (verhindert Import-Zirkus)."""
    try:
        from core import auth as _a
        return _a
    except Exception:
        return importlib.import_module("core.auth")


def render_login_form(app_name: str, app_version: str) -> Tuple[str, str, bool]:
    """Zentrierte Login-UI, schmal, ohne Pille, mit Registrierung."""

    st.markdown(
        """
        <style>
        /* Sidebar ausblenden */
        [data-testid="stSidebar"] { display:none !important; }

        /* Hintergrund */
        body {
            background: radial-gradient(900px 500px at 20% -10%, #1e1b4b33, transparent),
                        radial-gradient(900px 500px at 120% 0%, #0f766e33, transparent),
                        #0b0b12;
        }

        /* Container verkleinern & zentrieren */
        [data-testid="block-container"] {
            max-width: 520px !important;
            margin: 0 auto !important;
            padding-top: 8vh !important;
            text-align: center !important;  /* ZENTRIERT ALLES */
        }

        /* Erste Streamlit-Pille entfernen */
        [data-testid="block-container"] > div:first-child {
            display:none !important;
        }

        /* Buttons, Toolbar, Badges killen */
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stCloudAppStatus"],
        header [data-testid="stToolbar"],
        header [data-testid="stHeaderActionButtons"],
        header [data-testid="stActionButton"],
        .stDeployButton,
        .viewerBadge_container__r3R7,
        .viewerBadge_link__qRIco,
        button[title="Manage app"],
        button[title="View source"],
        [data-testid="baseButton-secondary"]:has(> div:empty),
        button:has(span:empty)
        { display:none !important; }

        /* Typografie */
        .ge-title {
            font-size: 1.6rem;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .ge-sub {
            font-size: .9rem;
            opacity: .78;
            margin-bottom: 10px;
        }
        .ge-version {
            font-size:.8rem;
            opacity:.55;
            margin-bottom: 24px;
        }
        .ge-footer {
            text-align:center;
            opacity:.6;
            font-size:.8rem;
            margin-top:30px;
            margin-bottom:10vh;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------- HEADER ----------
    st.markdown(f"<div class='ge-title'>{app_name} 🍸</div>", unsafe_allow_html=True)
    st.markdown("<div class='ge-sub'>Bitte melde dich an, um fortzufahren.</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='ge-version'>v{app_version}</div>", unsafe_allow_html=True)

    # ---------- LOGIN FORM ----------
    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input(
            "Benutzername", placeholder="username", key="ge_user"
        )

        password = st.text_input(
            "Passwort", placeholder="••••••••", type="password", key="ge_pass"
        )

        show_pw = st.checkbox("Passwort anzeigen", key="ge_showpw")
        if show_pw:
            st.text_input("Passwort (sichtbar)", value=password, type="default")

        st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
        pressed_login = st.form_submit_button("Einloggen", use_container_width=True)

    st.markdown("---")

    # ---------- REGISTRIERUNG ----------
    with st.expander("Noch kein Konto? Jetzt registrieren", expanded=False):
        with st.form("ge_register_form", clear_on_submit=True):

            r_user = st.text_input("Benutzername (öffentlich)", key="reg_user")
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
                        st.info("Sobald ein Admin freigibt, ist der Login möglich.")
                    else:
                        st.error(msg)
                except Exception as e:
                    st.error("Registrierung fehlgeschlagen (interner Fehler).")
                    st.exception(e)

    # ---------- FOOTER ----------
    st.markdown("<div class='ge-footer'>© O-der Klub · Gastro Essentials</div>", unsafe_allow_html=True)

    return (username or "").strip(), (password or ""), bool(pressed_login)
