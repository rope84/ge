# login_view.py
import streamlit as st

def render_login_form(app_name: str, app_version: str):
    # Kein set_page_config hier – das macht app.py!
    st.markdown("""
        <style>
        .ge-login-wrap{min-height:100vh;display:grid;place-items:center;background:radial-gradient(1000px 500px at 70% 10%, #132036 0%, #0b0b12 60%, #09090f 100%)}
        .ge-login-card{width:min(420px,92vw);padding:28px 24px;border-radius:18px;background:#17171f;
            box-shadow:0 10px 40px rgba(0,0,0,.55);color:#e9e9ef}
        .ge-login-card h1{margin:0 0 6px 0;font-size:1.5rem}
        .ge-login-card p{margin:0 0 20px 0;opacity:.75}
        .ge-login-foot{margin-top:14px;font-size:.8rem;opacity:.6;text-align:center}
        /* Nervige „Pille“/leere Buttons unterbinden: */
        [data-testid="baseButton-secondary"]:has(> div:empty),
        button:has(span:empty){display:none !important}
        /* Streamlit Deploy-/Toolbar ausblenden: */
        [data-testid="stDecoration"], [data-testid="stToolbar"] { display:none !important }
        </style>
        <div class="ge-login-wrap"><div class="ge-login-card">
    """, unsafe_allow_html=True)

    st.markdown(f"<h1>{app_name} 🍸</h1>", unsafe_allow_html=True)
    st.markdown(f"<p>Version {app_version}</p>", unsafe_allow_html=True)

    u = st.text_input("Benutzername", placeholder="z. B. oklub")
    p = st.text_input("Passwort", type="password", placeholder="••••••••")
    pressed = st.button("Einloggen", use_container_width=True)

    st.markdown('<div class="ge-login-foot">© O-der Klub · Gastro Essentials</div></div></div>',
                unsafe_allow_html=True)
    return u.strip(), p, pressed
