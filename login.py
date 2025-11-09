# login.py
import streamlit as st

def render_login_form(app_name: str, app_version: str):
    """
    Minimaler Login ohne Box/Pille:
    - Kein Container/Gradient/Shadow
    - Zentriert, schmale Breite
    - Version rechts oben
    Rückgabe: (username, password, pressed)
    """

    # ---- Nur Login-Ansicht stylen (ohne Box) ----
    st.markdown(
        """
        <style>
        /* Sidebar & Deko ausblenden */
        [data-testid="stSidebar"] { display:none !important; }
        [data-testid="stDecoration"], [data-testid="stToolbar"] { display:none !important; }

        /* Haupt-Container schmal & zentriert, auch bei layout="wide" */
        .block-container {
            max-width: 480px !important;
            padding-top: 10vh !important;
            margin: 0 auto !important;
        }

        /* Ruhiger, einfarbiger Hintergrund (keine „Pille“) */
        body { background: #0b0b12 !important; }

        /* Headline + Badge */
        .login-headline { font-size: 1.35rem; font-weight: 700; margin: 0; color: #e5e7eb; }
        .login-sub      { font-size: .92rem;  opacity: .75;   margin: 2px 0 16px 0; color: #e5e7eb; }
        .login-badge    { text-align:right; opacity:.65; font-size:.85rem; }

        /* Inputs */
        input[type="text"], input[type="password"]{
            border-radius:12px !important;
            border:1px solid rgba(255,255,255,.18) !important;
            padding:10px 12px !important;
            background: rgba(255,255,255,.03) !important;
            color:#e5e7eb !important;
            box-shadow:none !important;
        }
        input[type="text"]:focus, input[type="password"]:focus{
            border-color:#0A84FF !important;
            box-shadow:0 0 0 4px rgba(10,132,255,.25) !important;
        }

        /* Button */
        button[kind="primary"]{
            border-radius:12px !important;
            background:#0A84FF !important;
            color:#fff !important; font-weight:600 !important;
        }
        button[kind="primary"]:hover{ filter:brightness(1.06); transform:translateY(-1px); }

        /* Fußzeile */
        .login-footer { text-align:center; opacity:.65; font-size:.8rem; margin-top: 12px; }

        /* Sicherheitsnetz: leere „Pillen“-Buttons ggf. verstecken */
        button:empty { display:none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---- Kopf (links Titel/Untertitel, rechts Version) – ohne Box ----
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"<div class='login-headline'>{app_name} 🍸</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-sub'>Bitte melde dich an, um fortzufahren.</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='login-badge'>v{app_version}</div>", unsafe_allow_html=True)

    # ---- Formular (Enter-Submit) ----
    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input("Benutzername", placeholder="z. B. oklub", key="ge_user")
        show_pw  = st.checkbox("Passwort anzeigen", value=False, key="ge_showpw")
        pw_type  = "default" if show_pw else "password"
        password = st.text_input("Passwort", type=pw_type, placeholder="••••••••", key="ge_pass")
        st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
        pressed = st.form_submit_button("Einloggen", use_container_width=True)

    st.markdown("<div class='login-footer'>© O-der Klub · Gastro Essentials</div>", unsafe_allow_html=True)

    return (username or "").strip(), (password or ""), bool(pressed)
