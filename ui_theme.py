def render_login_form(app_name: str, app_version: str):
    import streamlit as st

    # --- Styling ---
    st.markdown(
        """
        <style>
        body {
            background: radial-gradient(circle at top left, #181818, #0c0c0c);
        }
        .login-box {
            max-width: 400px;
            margin: 12vh auto;
            background-color: #1f1f1f;
            padding: 36px 30px;
            border-radius: 16px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            text-align: center;
            color: white;
        }
        .login-box h1 { font-size: 1.6rem; margin-bottom: 6px; }
        .login-box p { opacity: 0.8; margin-bottom: 20px; font-size: .9rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # --- Inhalt ---
    st.markdown("<div class='login-box'>", unsafe_allow_html=True)
    st.markdown(f"<h1>{app_name} 🍸</h1>", unsafe_allow_html=True)
    st.markdown(f"<p>Version {app_version} · Zugang zum O-der Klub Dashboard</p>", unsafe_allow_html=True)

    username = st.text_input("Benutzername", placeholder="z. B. oklub")
    password = st.text_input("Passwort", placeholder="••••••••", type="password")
    pressed = st.button("Login", use_container_width=True)

    st.markdown("<br><small>Probleme beim Login? Kontaktiere den Admin.</small>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    return username.strip(), password, pressed
