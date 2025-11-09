# login.py
import streamlit as st
from core import auth  # für register_user()

def render_login_form(app_name: str, app_version: str):
    """
    Login-Seite mit optionaler Registrierung.
    Rückgabe: (username, password, pressed_login)
    Registrierung ruft core.auth.register_user() auf und zeigt Message.
    """

    # --- Stil / Layout ---
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stDecoration"], [data-testid="stToolbar"] {
            display:none !important;
        }
        .block-container {
            max-width: 640px !important;
            padding-top: 12vh !important;
            margin: 0 auto !important;
        }
        body { background:#0b0b12 !important; }

        .login-headline { font-size: 1.45rem; font-weight: 700; margin: 0; color: #e5e7eb; }
        .login-sub      { font-size: .95rem;  opacity: .75; margin: 4px 0 18px 0; color: #e5e7eb; }
        .login-badge    { text-align:right; opacity:.65; font-size:.9rem; }

        input[type="text"], input[type="password"], input[type="email"]{
            border-radius:12px !important;
            border:1px solid rgba(255,255,255,.18) !important;
            padding:12px 14px !important;
            background: rgba(255,255,255,.03) !important;
            color:#e5e7eb !important;
            box-shadow:none !important;
        }
        input[type="text"]:focus, input[type="password"]:focus, input[type="email"]:focus{
            border-color:#0A84FF !important;
            box-shadow:0 0 0 4px rgba(10,132,255,.25) !important;
        }
        button[kind="primary"]{
            border-radius:12px !important;
            background:#0A84FF !important;
            color:#fff !important;
            font-weight:600 !important;
        }
        .login-footer { text-align:center; opacity:.65; font-size:.8rem; margin-top: 16px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    show_register = st.session_state.get("_show_register", False)

    # Header
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"<div class='login-headline'>{app_name} 🍸</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='login-sub'>Bitte melde dich an – oder registriere dich neu.</div>",
            unsafe_allow_html=True
        )
    with c2:
        st.markdown(f"<div class='login-badge'>v{app_version}</div>", unsafe_allow_html=True)

    # Umschalter
    switch_col1, switch_col2 = st.columns([1,1])
    with switch_col1:
        if not show_register and st.button("Neu registrieren", use_container_width=True):
            st.session_state["_show_register"] = True
            st.rerun()
    with switch_col2:
        if show_register and st.button("Zurück zum Login", use_container_width=True):
            st.session_state["_show_register"] = False
            st.rerun()

    # ---------------- Login ----------------
    if not show_register:
        with st.form("ge_login_form", clear_on_submit=False):
            username = st.text_input("Benutzername", placeholder="username", key="ge_user")
            password = st.text_input("Passwort", type="password", placeholder="••••••••", key="ge_pass")
            show_pw  = st.checkbox("Passwort anzeigen", value=False, key="ge_showpw")
            if show_pw:
                st.text_input("Passwort (sichtbar)", value=password, type="default", key="ge_pass_visible_field")
            st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
            pressed = st.form_submit_button("Einloggen", use_container_width=True)

        st.markdown("<div class='login-footer'>© O-der Klub · Gastro Essentials</div>", unsafe_allow_html=True)
        return (username or "").strip(), (password or ""), bool(pressed)

    # ---------------- Registrierung ----------------
    else:
        with st.form("ge_register_form", clear_on_submit=False):
            st.subheader("Registrieren")
            colA, colB = st.columns(2)
            with colA:
                first_name = st.text_input("Vorname", key="reg_fn")
            with colB:
                last_name = st.text_input("Nachname", key="reg_ln")
            email    = st.text_input("E-Mail", key="reg_mail", placeholder="name@example.com")
            username = st.text_input("Benutzername", key="reg_user", placeholder="username")
            pw1      = st.text_input("Passwort", key="reg_pw1", type="password")
            pw2      = st.text_input("Passwort wiederholen", key="reg_pw2", type="password")

            st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
            submit_reg = st.form_submit_button("Registrierung absenden", use_container_width=True)

        if submit_reg:
            if pw1 != pw2:
                st.error("Passwörter stimmen nicht überein.")
            else:
                ok, msg = auth.register_user(username, first_name, last_name, email, pw1)
                if ok:
                    st.success(msg)
                    st.info("Du bekommst Zugang, sobald ein Admin dich freigibt.")
                    # danach zurück zum Login
                    st.session_state["_show_register"] = False
                else:
                    st.error(msg)

        st.markdown("<div class='login-footer'>© O-der Klub · Gastro Essentials</div>", unsafe_allow_html=True)
        # Bei Registration liefern wir kein Login-Result
        return "", "", False
