# login.py
import streamlit as st

def render_login_form(app_name: str, app_version: str):
    """
    Zeigt eine zentrierte Login-Karte an.
    Rückgabe: (username, password, pressed)
    Kein set_page_config hier – das macht app.py!
    """

    # --- Hardening & sauberes Layout nur für die Login-Ansicht ---
    st.markdown("""
        <style>
        /* Sidebar auf der Login-Seite ausblenden */
        [data-testid="stSidebar"] { display: none !important; }
        /* Haupt-Container schmal & zentriert, auch bei layout="wide" */
        .block-container {
            max-width: 460px !important;
            padding-top: 10vh !important;
            margin: 0 auto !important;
        }
        /* dezenter Verlaufshintergrund */
        body {
            background: radial-gradient(900px 500px at 20% -10%, #1e1b4b33, transparent),
                        radial-gradient(900px 500px at 120% 0%, #0f766e33, transparent),
                        #0b0b12;
        }
        .ge-card {
            background: rgba(20,20,28,0.96);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            box-shadow: 0 18px 50px rgba(0,0,0,0.45);
            padding: 26px 22px;
            color: #e5e7eb;
        }
        .ge-title { font-size: 1.35rem; font-weight: 700; margin: 0 0 6px 0; }
        .ge-sub   { font-size: .85rem; opacity: .75; margin: 0 0 16px 0; }
        .ge-badge { display:inline-block; font-size:.72rem; padding:2px 8px;
                    border-radius:999px; border:1px solid #ffffff22; opacity:.85; }
        .ge-footer{ text-align:center; opacity:.65; font-size:.8rem; margin-top: 14px; }
        </style>
    """, unsafe_allow_html=True)

    # --- Karte ---
    st.markdown("<div class='ge-card'>", unsafe_allow_html=True)
    c1, c2 = st.columns([1,1])
    with c1:
        st.markdown(f"<div class='ge-title'>{app_name} 🍸</div>", unsafe_allow_html=True)
        st.markdown("<div class='ge-sub'>Bitte melde dich an, um fortzufahren.</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div style='text-align:right' class='ge-badge'>v{app_version}</div>", unsafe_allow_html=True)
}
    # Form = Enter-Submit + keine Widget-Key-Konflikte
    with st.form("ge_login_form", clear_on_submit=False):
        username = st.text_input("Benutzername", placeholder="z. B. oklub", key="ge_user")
        show_pw  = st.checkbox("Passwort anzeigen", value=False, key="ge_showpw")
        pw_type  = "default" if show_pw else "password"
        password = st.text_input("Passwort", type=pw_type, placeholder="••••••••", key="ge_pass")

        st.caption("Hinweis: Mind. 6 Zeichen, 1 Großbuchstabe, 1 Sonderzeichen.")
        pressed = st.form_submit_button("Einloggen", use_container_width=True)

    st.markdown("<div class='ge-footer'>© O-der Klub · Gastro Essentials</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Rückgabe wie gehabt
    return (username or "").strip(), (password or ""), bool(pressed)
