# login.py
import streamlit as st

def render_login_form(app_name: str, app_version: str):
    st.set_page_config(page_title=f"{app_name} Login", page_icon="🍸", layout="centered")

    # --- Style ---
    st.markdown("""
        <style>
        body {
            background: linear-gradient(180deg, #101018 0%, #0b0b12 100%);
        }
        .login-card {
            max-width: 400px;
            margin: 10vh auto;
            padding: 40px 32px;
            background-color: #1b1b25;
            border-radius: 18px;
            box-shadow: 0 8px 28px rgba(0,0,0,0.5);
            text-align: center;
            color: #fff;
        }
        .login-card h1 {
            font-size: 1.6rem;
            margin-bottom: 4px;
        }
        .login-card p {
            font-size: 0.9rem;
            opacity: 0.85;
            margin-bottom: 24px;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- Inhalt ---
    st.markdown("<div class='login-card'>", unsafe_allow_html=True)
    st.markdown(f"<h1>{app_name} 🍸</h1>", unsafe_allow_html=True)
    st.markdown(f"<p>Version {app_version}</p>", unsafe_allow_html=True)

    username = st.text_input("Benutzername", placeholder="z. B. username")
    password = st.text_input("Passwort", type="password", placeholder="••••••••")
    pressed = st.button("Einloggen", use_container_width=True)

    st.markdown("<br><small>© O-der Klub · Gastro Essentials</small>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    return username.strip(), password, pressed
