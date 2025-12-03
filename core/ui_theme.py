from pathlib import Path
import streamlit as st

# ============================
# Farb- & Layout-Variablen
# ============================
PRIMARY_COLOR = "#0A84FF"
ACCENT_COLOR = "#E5E7EB"
TEXT_COLOR = "#E5E7EB"
MUTED_COLOR = "#9CA3AF"
CARD_BG = "#111827"
BODY_BG = "#0B0F18"

FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, "
    "Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif"
)

_ASSETS_CSS = Path(__file__).parent / "assets" / "style.css"
_CSS_LOADED_KEY = "_ge_theme_css_loaded"


# ============================
# CSS aktivieren
# ============================
def use_theme() -> None:
    """Einmal pro Session: CSS aus Assets + Fallback injizieren."""
    if st.session_state.get(_CSS_LOADED_KEY):
        return

    css = _DEFAULT_CSS()

    if _ASSETS_CSS.exists():
        try:
            css += "\n\n/* ---- assets/style.css ---- */\n" + _ASSETS_CSS.read_text(encoding="utf-8")
        except Exception:
            pass

    css += """
    /* globale UI-Elemente entfernen */
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"],
    .stDeployButton,
    .viewerBadge_container__r3R7,
    .viewerBadge_link__qRIco,
    button[title="Manage app"],
    button[title="View source"] { display: none !important; }

    header [data-testid="stToolbar"] { display: none !important; }
    .block-container { padding-top: 16px !important; }
    """

    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    st.session_state[_CSS_LOADED_KEY] = True


# ============================
# UI-Komponenten
# ============================
def page_header(title: str, subtitle: str = "", icon: str | None = None) -> None:
    icon_html = f"<span class='ge-title-icon'>{icon}</span>" if icon else ""
    sub_html = f"<p>{subtitle}</p>" if subtitle else ""
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
    help_block = f'<div class="ge-card-help">{help_text}</div>' if help_text else ""
    st.markdown(
        f"""
        <div class="ge-card">
            <div class="ge-card-title">{title}</div>
            <div class="ge-card-value">{value}</div>
            {help_block}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================
# Fallback-CSS (wenn style.css fehlt)
# ============================
def _DEFAULT_CSS() -> str:
    return f"""
    html, body, [class^="css"] {{
        font-family: {FONT_STACK};
        color: {TEXT_COLOR};
        background: {BODY_BG};
    }}

    .block-container {{ padding-top: 16px !important; }}

    .ge-page-header {{
        margin: 0 0 1.0rem 0;
        padding: .25rem 0 .5rem 0;
        border-bottom: 1px solid rgba(255,255,255,.06);
    }}
    .ge-page-header h1 {{
        color: {ACCENT_COLOR};
        font-size: 1.6rem;
        line-height: 1.2;
        margin: 0;
        display: flex;
        align-items: center;
        gap: .5rem;
        font-weight: 700;
    }}
    .ge-page-header p {{
        color: {MUTED_COLOR};
        margin-top: .35rem;
        margin-bottom: 0;
        font-size: .95rem;
    }}
    .ge-title-icon {{ font-size: 1.25rem; transform: translateY(1px); }}

    .ge-section-title {{
        color: {ACCENT_COLOR};
        margin: 1.1rem 0 .6rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: .5rem;
    }}
    .ge-sec-icon {{ font-size: 1.05rem; transform: translateY(1px); }}

    .ge-card {{
        background: {CARD_BG};
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 14px;
        padding: 16px 18px;
        margin: 8px 0 12px;
        box-shadow: 0 6px 18px rgba(0,0,0,.20);
    }}
    .ge-card-title {{ font-size: .82rem; color: {MUTED_COLOR}; letter-spacing: .2px; }}
    .ge-card-value {{ font-size: 1.65rem; font-weight: 800; margin-top: 4px; }}
    .ge-card-help  {{ font-size: .8rem; color: {MUTED_COLOR}; margin-top: 6px; }}

    input[type="text"], input[type="password"] {{
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,.18) !important;
        padding: 10px 12px !important;
        background: rgba(255,255,255,.03) !important;
        color: {TEXT_COLOR} !important;
    }}
    input[type="text"]:focus, input[type="password"]:focus {{
        border-color: {PRIMARY_COLOR} !important;
        box-shadow: 0 0 0 4px rgba(10,132,255,.25) !important;
    }}
    button[kind="primary"] {{
        border-radius: 12px !important;
        background: {PRIMARY_COLOR} !important;
        color: #fff !important;
        font-weight: 600 !important;
    }}
    button[kind="primary"]:hover {{
        filter: brightness(1.06);
        transform: translateY(-1px);
    }}
    """
