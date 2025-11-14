# login.py
import streamlit as st
from typing import Tuple
import importlib


def _lazy_auth():
    """Lädt core.auth erst bei Bedarf (verhindert Zyklen)."""
    try:
        from core import auth
        return auth
    except Exception:
        return importlib.import_module("core.auth")


def render_login_form(app_name: str, app_version: str) -> Tuple[str, str, bool]:
    """
    Zeichnet die Login-Card.
    Rückgabe: (username, password, pressed_login)
    Registrierung wird intern behandelt (Message-Feedback), beeinflusst Rückgabe nicht.
    """

    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }

        body {
            background: radial-gradient(900px 500px at 20% -10%, #1e1b4b33, transparent),
                        radial-gradient(900px 500px at 120% 0%, #0f766e33, transparent),
                        #0b0b12;
        }
        .ge-card {
            max-width: 720px;
            margin: 6vh auto 4vh auto;
            background: rgba(20,20,28,0.96);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            box-shadow: 0 18px 50px rgba(0,0,0,0.45);
            padding: 26px 26px;
            color: #e5e7eb;
        }
        .ge-title { font-size: 1.35rem; font-weight: 700; margin: 0 0 6px 0; }
        .ge-sub   { font-size: .85rem; opacity: .75; margin: 0 0 16px 0; }
        .ge-badge { display:inline-block; font-size:.72rem; padding:2px 8px;
                    border-radius:999px; border:1px solid #ffffff22; opacity:.85; }
        .ge-footer{ text-align:center; opacity:.65; font-size:.8rem; margin-top: 14px; }

        [data-testid="stDecoration"], [data-testid="stToolbar"],
        [data-testid="baseButton-secondary"]:has(> div:empty),
        button:has(span:empty) { display:none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---- Karte
    st.markdown("<div class='ge-card'>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown(
            f"<div class='ge-title'>{app_name} 🍸</div>", unsafe_allow_html=True
        )
        st.markdown(
            "<div class='ge-sub'>Bitte melde dich an, um fortzufahren.</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div style='text-align:right' class='ge-badge'>v{app_version}</div>",
            unsafe_allow_html=True,
        )

    # ---- Login-Form
    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input(
            "Benutzername", placeholder="username", key="ge_user"
        )
        password = st.text_input(
            "Passwort", type="password", placeholder="••••••••", key="ge_pass"
        )
        show_pw = st.checkbox("Passwort anzeigen", value=False, key="ge_showpw")
        if show_pw:
            st.info(
                "Passwort-Anzeige aktiv. Tippe erneut, um es im Klartext zu sehen."
            )
            st.text_input(
                "Passwort (sichtbar)",
                value=password,
                type="default",
                key="ge_pass_visible",
            )

        st.caption(
            "Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen."
        )
        pressed_login = st.form_submit_button("Einloggen", use_container_width=True)

    st.markdown("---")

    # ---- Registrierung
    with st.expander("Noch kein Konto? Jetzt registrieren", expanded=False):
        with st.form("ge_register_form", clear_on_submit=True):
            r_user = st.text_input("Benutzername (öffentlich)", key="reg_user")
            r_fn = st.text_input("Vorname", key="reg_fn")
            r_ln = st.text_input("Nachname", key="reg_ln")
            r_mail = st.text_input("E-Mail", key="reg_mail")
            r_pw = st.text_input("Passwort", type="password", key="reg_pw")
            r_pw2 = st.text_input(
                "Passwort wiederholen", type="password", key="reg_pw2"
            )
            submit_reg = st.form_submit_button(
                "Registrierung absenden", use_container_width=True
            )

        if submit_reg:
            if r_pw != r_pw2:
                st.error("Passwörter stimmen nicht überein.")
            else:
                try:
                    auth = _lazy_auth()
                    ok, msg = auth.register_user(r_user, r_fn, r_ln, r_mail, r_pw)
                    if ok:
                        st.success(msg)
                        st.info(
                            "Sobald ein Admin freigibt, ist der Login möglich."
                        )
                    else:
                        st.error(msg)
                except Exception as e:
                    st.error("Registrierung fehlgeschlagen (interner Fehler).")
                    st.exception(e)

    st.markdown(
        "<div class='ge-footer'>© O-der Klub · Gastro Essentials</div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    return (username or "").strip(), (password or ""), bool(pressed_login)
