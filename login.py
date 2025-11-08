# login.py
import streamlit as st

def render_login_form(app_name: str, app_version: str):
    """
    Rendered a centered, clean login card.
    Rückgabe-Signatur bleibt: (username, password, pressed)
    Keine set_page_config() hier – das macht app.py!
    """

    # ---- Styles (nur auf der Login-Ansicht sichtbar) ----
    st.markdown("""
        <style>
        .ge-login-wrap {
            min-height: 88vh;
            display: grid;
            place-items: center;
            background: radial-gradient(1200px 600px at 20% -10%, #1e1b4b33, transparent),
                        radial-gradient(1000px 500px at 120% 10%, #0f766e33, transparent);
        }
        .ge-login-card {
            width: 100%;
            max-width: 420px;
            background: rgba(20, 20, 28, 0.95);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            box-shadow: 0 18px 50px rgba(0,0,0,0.45);
            padding: 26px 24px;
            color: #e5e7eb;
        }
        .ge-login-title {
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: 0.2px;
            margin: 0 0 6px 0;
        }
        .ge-login-sub {
            font-size: 0.85rem;
            opacity: 0.75;
            margin-bottom: 18px;
        }
        .ge-inline {
            display:flex; gap:10px; align-items:center; justify-content:space-between;
        }
        .ge-hint {
            font-size: 0.8rem; opacity: 0.75; margin-top: 6px;
        }
        .ge-footer {
            text-align:center; opacity:.65; font-size:.8rem; margin-top: 18px;
        }
        .ge-badge {
            display:inline-block; font-size:.72rem; padding:2px 8px;
            border-radius:999px; border:1px solid #ffffff22; opacity:.85;
        }
        </style>
    """, unsafe_allow_html=True)

    # ---- Layout ----
    st.markdown("<div class='ge-login-wrap'><div class='ge-login-card'>", unsafe_allow_html=True)

    st.markdown(f"""
        <div class="ge-inline">
            <div>
                <div class="ge-login-title">{app_name} 🍸</div>
                <div class="ge-login-sub">Bitte melde dich an, um fortzufahren.</div>
            </div>
            <div class="ge-badge">v{app_version}</div>
        </div>
    """, unsafe_allow_html=True)

    # Form verhindert „Widget-nachträglich-ändern“-Fehler und erlaubt Enter-Submit
    with st.form(key="ge_login_form", clear_on_submit=False):
        username = st.text_input("Benutzername", placeholder="z. B. oklub", key="ge_login_user")
        # Passwortfeld mit optionalem Anzeigen
        col1, col2 = st.columns([4,1])
        with col1:
            pw_type = "password" if not st.session_state.get("ge_login_showpw") else "default"
            password = st.text_input("Passwort", type=pw_type, placeholder="••••••••", key="ge_login_pw")
        with col2:
            st.toggle("👁️", key="ge_login_showpw", label_visibility="collapsed")
        st.markdown("<div class='ge-hint'>Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.</div>", unsafe_allow_html=True)

        pressed = st.form_submit_button("Einloggen", use_container_width=True)

    st.markdown("<div class='ge-footer'>© O-der Klub · Gastro Essentials</div>", unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

    # Rückgabe wie bisher – wichtig für app.py
    return (username or "").strip(), st.session_state.get("ge_login_pw", ""), bool(pressed)
