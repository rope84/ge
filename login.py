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
    """Zentrierter, moderner Login-Screen mit Registrierung."""

    st.markdown(
        """
        <style>
        /* Sidebar ausblenden */
        [data-testid="stSidebar"] { display:none !important; }

        /* Hintergrund */
        body {
            background: radial-gradient(900px 500px at 20% -10%, #1e1b4b33, transparent),
                        radial-gradient(900px 500px at 120% 0%, #0f766e33, transparent),
                        #020617;
        }

        /* Hauptcontainer schmäler & zentriert */
        [data-testid="block-container"] {
            max-width: 900px !important;
            margin: 0 auto !important;
            padding-top: 10vh !important;
            display: flex;
            flex-direction: column;
            align-items: center;       /* alles in die Mitte */
        }

        /* Entfernt die leere „Pille“/erste Box von Streamlit */
        [data-testid="block-container"] > div:first-child {
            display: none !important;
        }

        /* Head-Bereich */
        .ge-head {
            text-align: center;
            margin-bottom: 18px;
        }
        .ge-title {
            font-size: 1.7rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            margin-bottom: 4px;
        }
        .ge-sub {
            font-size: 0.9rem;
            opacity: 0.78;
            margin-bottom: 6px;
        }
        .ge-version {
            font-size: 0.8rem;
            opacity: 0.5;
            margin-bottom: 20px;
        }

        /* Glassmorphism-Card für Login */
        .ge-card {
            width: 100%;
            max-width: 520px;                  /* SCHMÄLER */
            margin: 0 auto 22px auto;
            padding: 22px 22px 20px 22px;
            border-radius: 22px;
            border: 1px solid rgba(255,255,255,0.09);
            background: linear-gradient(
                            135deg,
                            rgba(15,23,42,0.96),
                            rgba(30,64,175,0.85)
                        );
            background-blend-mode: overlay;
            box-shadow:
                0 24px 60px rgba(0,0,0,0.7),
                0 0 0 1px rgba(255,255,255,0.02);
            backdrop-filter: blur(18px);
        }

        /* Expander schmäler halten */
        .ge-wrapper > div[data-testid="stExpander"] {
            width: 100%;
            max-width: 520px;
            margin: 0 auto;
        }

        /* Footer */
        .ge-footer {
            text-align:center;
            opacity:.6;
            font-size:.8rem;
            margin-top: 26px;
            margin-bottom: 10vh;
        }

        /* Diverse Streamlit-Badges / Toolbar verstecken */
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
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------- HEAD (zentriert) ----------
    st.markdown(
        f"""
        <div class="ge-head">
            <div class="ge-title">{app_name} 🍸</div>
            <div class="ge-sub">Bitte melde dich an, um fortzufahren.</div>
            <div class="ge-version">v{app_version}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- LOGIN-CARD ----------
    st.markdown("<div class='ge-card'>", unsafe_allow_html=True)

    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input("Benutzername", placeholder="username", key="ge_user")
        password = st.text_input("Passwort", type="password", placeholder="••••••••", key="ge_pass")

        show_pw = st.checkbox("Passwort anzeigen", key="ge_showpw")
        if show_pw:
            st.text_input("Passwort (sichtbar)", value=password, type="default", key="ge_pass_visible")

        st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
        pressed_login = st.form_submit_button("Einloggen", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ---------- REGISTRIERUNG (unter der Card, gleich breit) ----------
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
    st.markdown(
        "<div class='ge-footer'>© O-der Klub · Gastro Essentials</div>",
        unsafe_allow_html=True,
    )

    return (username or "").strip(), (password or ""), bool(pressed_login)
