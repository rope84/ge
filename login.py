# login.py
import streamlit as st
from typing import Tuple
import importlib
from core.db import conn


def _lazy_auth():
    """Lädt core.auth nur bei Bedarf (verhindert Import-Zirkus)."""
    try:
        from core import auth as _a
        return _a
    except Exception:
        return importlib.import_module("core.auth")


def _get_business_name(fallback: str) -> str:
    """Liest den Betriebsnamen aus meta.business_name, sonst fallback."""
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
    return fallback


def render_login_form(app_name: str, app_version: str) -> Tuple[str, str, bool]:
    """Zentrierter Login mit Betriebsnamen, ohne nervige Pille."""

    business_name = _get_business_name(app_name)

    st.markdown(
        f"""
        <style>
        /* Sidebar ausblenden */
        [data-testid="stSidebar"] {{ display:none !important; }}

        /* Hintergrund */
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

        /* Diese mysteriöse „Pille“ (gradient mit großer Rundung) killen */
        div[style*="border-radius: 999px"][style*="linear-gradient"],
        div[style*="border-radius:999px"][style*="linear-gradient"] {{
            display: none !important;
        }}

        /* Login-Form wirklich schmäler machen */
        div[data-testid="stForm"] {{
            max-width: 520px !important;
            margin: 0 auto !important;
        }}

        /* Head-Bereich */
        .ge-head {{
            text-align: center;
            margin-bottom: 10px;
        }}
        .ge-title {{
            font-size: 1.7rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            margin-bottom: 4px;
        }}
        .ge-sub {{
            font-size: 0.9rem;
            opacity: 0.78;
            margin-bottom: 4px;
        }}
        .ge-version {{
            font-size: 0.8rem;
            opacity: 0.5;
            margin-bottom: 24px;
        }}

        /* Glass-Card Look für das Form-Wrapper-Div */
        div[data-testid="stForm"] > div:first-child {{
            border-radius: 22px !important;
            border: 1px solid rgba(255,255,255,0.09) !important;
            background: linear-gradient(
                            135deg,
                            rgba(15,23,42,0.96),
                            rgba(30,64,175,0.85)
                        ) !important;
            box-shadow:
                0 24px 60px rgba(0,0,0,0.7),
                0 0 0 1px rgba(255,255,255,0.02) !important;
            backdrop-filter: blur(18px);
            padding: 22px 22px 20px 22px !important;
        }}

        .ge-footer {{
            text-align:center;
            opacity:.6;
            font-size:.8rem;
            margin-top: 26px;
            margin-bottom: 10vh;
        }}

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
        {{ display:none !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------- HEAD (zentriert, mit Betriebsname) ----------
    st.markdown(
        f"""
        <div class="ge-head">
            <div class="ge-title">{business_name}</div>
            <div class="ge-sub">Bitte melde dich an, um fortzufahren.</div>
            <div class="ge-version">Gastro Essentials · v{app_version}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- LOGIN-FORM ----------
    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input("Benutzername", placeholder="username", key="ge_user")
        password = st.text_input("Passwort", type="password", placeholder="••••••••", key="ge_pass")

        show_pw = st.checkbox("Passwort anzeigen", key="ge_showpw")
        if show_pw:
            st.text_input("Passwort (sichtbar)", value=password, type="default", key="ge_pass_visible")

        st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
        pressed_login = st.form_submit_button("Einloggen", use_container_width=True)

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
    st.markdown(
        "<div class='ge-footer'>© O-der Klub · Gastro Essentials</div>",
        unsafe_allow_html=True,
    )

    return (username or "").strip(), (password or ""), bool(pressed_login)
