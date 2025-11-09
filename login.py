# login.py
import streamlit as st

def render_login_form(app_name: str, app_version: str):
    """
    Minimaler Login ohne Box/Pille – überarbeitet:
    - Breiteres Layout
    - Checkbox unter Passwortfeld
    - Placeholder: 'username'
    Rückgabe: (username, password, pressed)
    """

    # ---- Stildefinition (leicht breiter & spacing optimiert) ----
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stDecoration"], [data-testid="stToolbar"] {
            display:none !important;
        }

        /* Breitere, zentrierte Fläche */
        .block-container {
            max-width: 620px !important;
            padding-top: 12vh !important;
            margin: 0 auto !important;
        }

        body { background: #0b0b12 !important; }

        /* Kopfbereich */
        .login-headline { font-size: 1.45rem; font-weight: 700; margin: 0; color: #e5e7eb; }
        .login-sub      { font-size: .95rem;  opacity: .75; margin: 4px 0 18px 0; color: #e5e7eb; }
        .login-badge    { text-align:right; opacity:.65; font-size:.9rem; }

        /* Eingabefelder */
        input[type="text"], input[type="password"]{
            border-radius:12px !important;
            border:1px solid rgba(255,255,255,.18) !important;
            padding:12px 14px !important;
            background: rgba(255,255,255,.03) !important;
            color:#e5e7eb !important;
            box-shadow:none !important;
        }
        input[type="text"]:focus, input[type="password"]:focus{
            border-color:#0A84FF !important;
            box-shadow:0 0 0 4px rgba(10,132,255,.25) !important;
        }

        /* Buttons */
        button[kind="primary"]{
            border-radius:12px !important;
            background:#0A84FF !important;
            color:#fff !important;
            font-weight:600 !important;
        }
        button[kind="primary"]:hover{
            filter:brightness(1.06);
            transform:translateY(-1px);
        }

        /* Fußzeile */
        .login-footer { text-align:center; opacity:.65; font-size:.8rem; margin-top: 16px; }

        /* Sicherheitsnetz */
        button:empty { display:none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---- Kopf (Titel + Version) ----
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"<div class='login-headline'>{app_name} 🍸</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-sub'>Bitte melde dich an, um fortzufahren.</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='login-badge'>v{app_version}</div>", unsafe_allow_html=True)

    # ---- Formular ----
    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input("Benutzername", placeholder="username", key="ge_user")
        password = st.text_input("Passwort", type="password", placeholder="••••••••", key="ge_pass")
        show_pw  = st.checkbox("Passwort anzeigen", value=False, key="ge_showpw")

        # Dynamisches Umschalten
        if show_pw:
            st.session_state["ge_pass_visible"] = st.text_input(
                "Passwort (sichtbar)",
                value=password,
                type="default",
                key="ge_pass_visible_field"
            )

        st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
        pressed = st.form_submit_button("Einloggen", use_container_width=True)

    st.markdown("<div class='login-footer'>© O-der Klub · Gastro Essentials</div>", unsafe_allow_html=True)

    return (username or "").strip(), (password or ""), bool(pressed)
