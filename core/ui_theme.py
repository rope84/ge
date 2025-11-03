# ui_theme.py
from pathlib import Path
import streamlit as st
from core.config import APP_NAME, APP_VERSION

# =========================
#  Farb- & Layout-Variablen
# =========================
PRIMARY_COLOR = "#0A84FF"   # Apple-ähnliches Blau für Akzente
ACCENT_COLOR  = "#E5E7EB"   # Helle Akzentfarbe für Dark-UI Überschriften
TEXT_COLOR    = "#E5E7EB"   # Standard-Textfarbe (Dark)
MUTED_COLOR   = "#9CA3AF"   # Sekundärtext
CARD_BG       = "#111827"   # Kartenhintergrund (Dark)
BODY_BG       = "#0B0F18"   # Seitenhintergrund (Dark)

FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, "
    "Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif"
)

_ASSETS_CSS     = Path(__file__).parent / "assets" / "style.css"
_CS_LOADED_KEY  = "_ge_theme_css_loaded"


# =========================
#  CSS laden
# =========================
def use_theme() -> None:
    """Einmalig pro Session CSS injizieren."""
    if st.session_state.get(_CS_LOADED_KEY):
        return

    # Basis-CSS (Fallback)
    css = _DEFAULT_CSS()

    # Optional: zusätzliche styles aus assets/style.css
    if _ASSETS_CSS.exists():
        try:
            css += "\n" + _ASSETS_CSS.read_text(encoding="utf-8")
        except Exception:
            pass

    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    st.session_state[_CS_LOADED_KEY] = True


# =========================
#  UI-Helfer
# =========================
def page_header(title: str, subtitle: str = "", icon: str | None = None) -> None:
    icon_html = f"<span class='ge-title-icon'>{icon}</span>" if icon else ""
    sub_html  = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f"""
        <div class="ge-page-header">
            <h1>{icon_html}{title}</h1>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, icon: str | None = None) -> None:
    icon_html = f"<span class='ge-sec-icon'>{icon}</span>" if icon else ""
    st.markdown(
        f"<h3 class='ge-section-title'>{icon_html}{title}</h3>",
        unsafe_allow_html=True,
    )


def small_footer(left_html: str) -> None:
    st.sidebar.markdown(
        f"<div class='ge-side-footer'>{left_html}</div>",
        unsafe_allow_html=True,
    )


def metric_card(title: str, value: str, help_text: str = "") -> None:
    st.markdown(
        f"""
        <div class="ge-card">
            <div class="ge-card-title">{title}</div>
            <div class="ge-card-value">{value}</div>
            {'<div class="ge-card-help">'+help_text+'</div>' if help_text else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login_form(app_name: str, version: str):
    """
    Zeichnet eine kompakte Login-Card (oben mit leichtem Abstand).
    Rückgabe: (username, password, pressed)
    """
    st.markdown("<div class='ge-login-wrap'>", unsafe_allow_html=True)
    st.markdown("<div class='ge-login-card'>", unsafe_allow_html=True)

    st.markdown("<div class='ge-login-logo'>🍸</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='ge-login-title'>{app_name}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='ge-login-sub'>{version}</div>", unsafe_allow_html=True)

    u = st.text_input("Benutzername")
    p = st.text_input("Passwort", type="password")
    pressed = st.button("Anmelden", use_container_width=True)

    st.markdown(
        "<div class='ge-login-help'>Passwort vergessen? "
        "<span>Bitte Administrator kontaktieren.</span></div>",
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)  # .ge-login-card
    st.markdown("</div>", unsafe_allow_html=True)  # .ge-login-wrap
    return u, p, pressed


# =========================
#  Fallback-CSS
# =========================
def _DEFAULT_CSS() -> str:
    # Alle Farben direkt eingesetzt (keine Platzhalter, keine Ersetzungen)
    return f"""
    html, body, [class^="css"] {{
        font-family: {FONT_STACK};
        color: {TEXT_COLOR};
        background: {BODY_BG};
    }}

    /* Kopfbereich */
    .ge-page-header{{
        margin: 0 0 1.0rem 0;
        padding: .25rem 0 .5rem 0;
        border-bottom: 1px solid rgba(255,255,255,.06);
    }}
    .ge-page-header h1{{
        color: {ACCENT_COLOR};
        font-size: 1.6rem;
        line-height: 1.2;
        margin: 0;
        display: flex;
        align-items: center;
        gap: .5rem;
        font-weight: 700;
    }}
    .ge-page-header p{{
        color: {MUTED_COLOR};
        margin-top: .35rem;
        margin-bottom: 0;
        font-size: .95rem;
    }}
    .ge-title-icon{{ font-size: 1.25rem; transform: translateY(1px); }}

    /* Sektionstitel */
    .ge-section-title{{
        color: {ACCENT_COLOR};
        margin: 1.1rem 0 .6rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: .5rem;
    }}
    .ge-sec-icon{{ font-size: 1.05rem; transform: translateY(1px); }}

    /* Cards / KPIs */
    .ge-card{{
        background: {CARD_BG};
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 14px;
        padding: 16px 18px;
        margin: 8px 0 12px;
        box-shadow: 0 6px 18px rgba(0,0,0,.20);
    }}
    .ge-card-title{{ font-size: .82rem; color: {MUTED_COLOR}; letter-spacing: .2px; }}
    .ge-card-value{{ font-size: 1.65rem; font-weight: 800; margin-top: 4px; }}
    .ge-card-help{{  font-size: .8rem;  color: {MUTED_COLOR}; margin-top: 6px; }}

    /* Sidebar Footer */
    .ge-side-footer{{
        position: fixed;
        left: 14px; bottom: 10px;
        font-size: 10px; opacity: .65;
    }}
    section[data-testid="stSidebar"] label p {{ margin-bottom: 4px; }}

    /* -------- Login -------- */
    .ge-login-wrap{{
        min-height: 100vh;
        display: flex;
        align-items: flex-start;      /* nach oben ausrichten */
        justify-content: center;
        padding-top: 6vh;             /* kleiner Abstand oben */
        background: transparent;      /* kein farbiger Block */
    }}
    .ge-login-card{{
        width: min(520px, 96%);
        background: {CARD_BG};
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 16px;
        padding: 22px 20px;
        box-shadow: 0 14px 40px rgba(0,0,0,.35);
        backdrop-filter: blur(6px);
    }}
    .ge-login-logo{{
        font-size: 38px; line-height: 1; text-align: center;
        margin-top: .25rem;
    }}
    .ge-login-title{{
        text-align: center; font-weight: 700; font-size: 22px; margin-top: .25rem; color: {ACCENT_COLOR};
    }}
    .ge-login-sub{{
        text-align: center; color: {MUTED_COLOR}; font-size: 12px; margin-bottom: .9rem;
    }}
    .ge-login-help{{
        text-align: center; color: {MUTED_COLOR}; font-size: 12px; margin-top: .65rem;
    }}
    .ge-login-help span{{ color: {TEXT_COLOR}; opacity: .9; }}

    /* Inputs / Buttons (Streamlit) – dezente Apple-Optik */
    input[type="text"], input[type="password"]{{
        border-radius:12px !important;
        border:1px solid rgba(255,255,255,.18) !important;
        padding:10px 12px !important; box-shadow:none !important;
        background: rgba(255,255,255,.03) !important; color: {TEXT_COLOR} !important;
    }}
    input[type="text"]:focus, input[type="password"]:focus{{
        border-color: {PRIMARY_COLOR} !important;
        box-shadow: 0 0 0 4px rgba(10,132,255,.25) !important;
    }}
    button[kind="primary"]{{
        border-radius:12px !important;
        background: {PRIMARY_COLOR} !important;
        color:#fff !important; font-weight:600 !important;
    }}
    button[kind="primary"]:hover{{
        filter: brightness(1.06);
        transform: translateY(-1px);
    }}
    """
