# ui_theme.py
import streamlit as st
from base64 import b64encode
from typing import Tuple, Optional

# ===== Branding / Konfiguration =====
APP_LOGO_URL: Optional[str] = ""  # z.B. "https://…/logo.png" oder leer lassen
TAGLINE = "Zugang zum O-der Klub Operations Dashboard"

def use_theme():
    """Globales Styling (nach set_page_config aufrufen)."""
    st.markdown(
        """
        <style>
        /* Hintergrund */
        .stApp {
            background: radial-gradient(1200px 600px at 20% 0%, rgba(255,255,255,0.05), transparent 60%),
                        linear-gradient(180deg, #0b0b12 0%, #171722 50%, #0b0b12 100%);
        }
        /* Karten / Container Look */
        .ge-card {
            max-width: 520px;
            margin: 8vh auto 4vh auto;
            padding: 28px 26px;
            background: rgba(255,255,255,0.06);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 18px;
            box-shadow: 0 14px 36px rgba(0,0,0,0.35);
        }
        .ge-title { font-weight: 800; font-size: 1.6rem; letter-spacing: .2px; margin-bottom: 2px; }
        .ge-sub   { opacity: .9; font-size: .95rem; margin-bottom: 16px; }
        .ge-muted { opacity: .75; font-size: .85rem; }
        .ge-center { display:flex; justify-content:center; align-items:center; }
        .ge-footer { text-align:center; opacity:.65; font-size:.85rem; margin-top: 24px; }
        .ge-logo { border-radius: 14px; }
        .ge-pill { display:inline-block; padding:4px 10px; border-radius:999px; background:rgba(255,255,255,.08); font-size:.8rem; }
        </style>
        """,
        unsafe_allow_html=True
    )

def page_header(title: str, subtitle: str = ""):
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)

def small_footer(html_text: str):
    st.markdown(f"<div class='ge-footer'>{html_text}</div>", unsafe_allow_html=True)

def render_login_form(app_name: str, app_version: str) -> Tuple[str, str, bool]:
    """
    Zeichnet die Login-Seite und liefert (username, password, pressed).
    Passt 1:1 zu deinem app.py (login_screen ruft diese Funktion auf).
    """
    # Zentriertes Layout ohne Sidebar-Ablenkung
    st.markdown("<div class='ge-card'>", unsafe_allow_html=True)

    # Logo optional
    if APP_LOGO_URL:
        st.markdown("<div class='ge-center'>", unsafe_allow_html=True)
        st.image(APP_LOGO_URL, width=96, use_container_width=False)
        st.markdown("</div>", unsafe_allow_html=True)

    # Titel / Untertitel
    st.markdown(f"<div class='ge-title ge-center'>{app_name} 🍸</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='ge-sub ge-center'>{TAGLINE}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='ge-center' style='margin-bottom:14px;'>"
        f"<span class='ge-pill'>Version {app_version}</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    # Formular
    with st.form("ge_login_form", clear_on_submit=False):
        col1, col2 = st.columns([1, 1])
        with col1:
            username = st.text_input("Benutzername", placeholder="z. B. oklub / roman")
        with col2:
            show_pw = st.toggle("Passwort anzeigen", value=False)

        password = st.text_input(
            "Passwort",
            type=("default" if show_pw else "password"),
            placeholder="••••••••"
        )

        # Optional: „Angemeldet bleiben“ als QueryParam-Light
        remember = st.checkbox("Angemeldet bleiben")

        # CTA
        submitted = st.form_submit_button("Einloggen", use_container_width=True)

        # Kleiner Hinweis
        st.caption("Probleme beim Login? Wende dich an den Admin.")

        # Nach dem Submit: remember-Flag in Session parken (app.py kann es verwenden, wenn gewünscht)
        if submitted:
            st.session_state["remember_me"] = bool(remember)

    st.markdown("</div>", unsafe_allow_html=True)

    # Kleiner rechtlicher/Brand-Footer
    small_footer("© O-der Klub · Gastro Essentials · Interne Betriebsanwendung")

    return username.strip(), password, submitted
