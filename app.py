# app.py
import streamlit as st
import traceback

from core.db import setup_db
from core.auth import seed_admin_if_empty
from core import auth
from core.ui_theme import use_theme, page_header, small_footer
from login import render_login_form
from core.config import APP_NAME, APP_VERSION

# ---------------- Initial Setup ----------------
setup_db()
seed_admin_if_empty()

# ---------------- Dynamic Module Import ----------------
# ---------------- Dynamic Module Import ----------------
# ---------------- Dynamic Module Import ----------------
def import_modules():
    modules, errors = {}, {}

    def try_import(qualified_name: str):
        base = qualified_name.split(".")[-1]  # z.B. "start" aus "modules.start"
        try:
            mod = __import__(qualified_name, fromlist=["*"])
            fn = getattr(mod, f"render_{base}")  # erwartet z.B. render_start()
            modules[base] = fn
        except Exception as e:
            modules[base] = None
            errors[base] = f"{type(e).__name__}: {e}\n\n" + traceback.format_exc()

    for mod_name in ["start", "abrechnung", "dashboard", "inventur", "profile", "admin"]:
        try_import(f"modules.{mod_name}")

    return modules, errors

modules, import_errors = import_modules()

# ---------------- Session Init ----------------
def init_session():
    s = st.session_state
    s.setdefault("auth", False)
    s.setdefault("username", "")
    s.setdefault("role", "guest")
    s.setdefault("scope", "")
    s.setdefault("nav_choice", "Start")

init_session()

# ---------------- Auth ----------------
def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_session()
    st.rerun()

def login_screen():
    u, p, pressed = render_login_form(APP_NAME, APP_VERSION)
    if pressed:
        ok = getattr(auth, "_do_login")(u, p)
        if ok:
            st.session_state.auth = True
            st.session_state.username = u
            st.session_state.role = "admin" if u == "username" else (st.session_state.get("role") or "user")
            st.rerun()
        else:
            st.error("❌ Falscher Benutzername oder Passwort")

# ---------------- Fixed Footer ----------------
def fixed_footer():
    from core.config import APP_NAME, APP_VERSION
    import streamlit as st

    # CSS + HTML + Klickverhalten via Streamlit-Link
    st.markdown(
        f"""
        <style>
        .footer {{
            position: fixed;
            bottom: 10px;
            left: 0;
            width: 100%;
            text-align: center;
            font-size: 12px;
            color: gray;
            opacity: 0.85;
            line-height: 1.4em;
        }}
        .footer a {{
            color: #bbb;
            text-decoration: none;
            font-weight: bold;
        }}
        .footer a:hover {{
            color: white;
            text-decoration: underline;
        }}
        </style>

        <div class="footer">
            👤 <a href="?nav_choice=Profil">{st.session_state.get('username', 'Gast')}</a>
            &nbsp;·&nbsp;
            🧭 <span style='opacity:0.8'>{st.session_state.get('role', 'guest')}</span><br>
            <span style='opacity:0.7'>{APP_NAME} {APP_VERSION}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
# ---------------- Sidebar ----------------
def sidebar():
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(APP_VERSION)

        display_pages = ["Start", "Abrechnung", "Dashboard", "Inventur", "Profil"]
        if st.session_state.role == "admin":
            display_pages.append("Admin-Cockpit")

        choice_display = st.radio("Navigation", display_pages, label_visibility="collapsed")
        st.session_state.nav_choice = choice_display

        st.divider()
        if st.session_state.auth and st.button("Logout", use_container_width=True):
            logout()

def sidebar():
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(APP_VERSION)

        display_pages = ["Start", "Abrechnung", "Dashboard", "Inventur", "Profil"]
        if st.session_state.role == "admin":
            display_pages.append("Admin-Cockpit")

        choice_display = st.radio("Navigation", display_pages, label_visibility="collapsed")
        st.session_state.nav_choice = choice_display

        st.divider()

        if st.session_state.auth and st.button("Logout", use_container_width=True):
            logout()

        # 👇 Footer wird jetzt korrekt im Sidebar-Kontext gerendert
        fixed_footer()
# ---------------- Routing ----------------
DISPLAY_TO_MODULE = {
    "start": "start",
    "abrechnung": "abrechnung",
    "dashboard": "dashboard",
    "inventur": "inventur",
    "profil": "profile",
    "admin-cockpit": "admin",
}

def route():
    display_key = (st.session_state.get("nav_choice") or "Start").lower()
    mod_key = DISPLAY_TO_MODULE.get(display_key)
    if not mod_key:
        st.error(f"⚠️ Ungültige Seite: {display_key}")
        return

    mod_func = modules.get(mod_key)
    mod_err = import_errors.get(mod_key)

    if not mod_func:
        st.error(f"❌ Modul '{mod_key}.py' konnte nicht geladen werden.")
        st.code(mod_err or "Unbekannter Fehler", language="text")
        return

    try:
        if mod_key == "start":
            mod_func(st.session_state.username or "Gast")
        elif mod_key == "abrechnung":
            mod_func(st.session_state.role, st.session_state.scope)
        elif mod_key == "dashboard":
            mod_func()
        elif mod_key == "inventur":
            try:
                mod_func(st.session_state.username or "unknown", st.session_state.role or "guest")
            except TypeError:
                mod_func(st.session_state.username or "unknown")
        elif mod_key == "profile":
            mod_func(st.session_state.username or "")
        elif mod_key == "admin":
            if st.session_state.role != "admin":
                st.error("Kein Zugriff. Adminrechte erforderlich.")
            else:
                mod_func()
        else:
            st.error(f"Seite nicht implementiert: {mod_key}")
    except Exception:
        st.error(f"❌ Laufzeitfehler in '{mod_key}.py'")
        st.code(traceback.format_exc(), language="text")

# ---------------- Main ----------------
def main():
    st.set_page_config(page_title=APP_NAME, page_icon="🍸", layout="wide")
    use_theme()  # CSS erst NACH set_page_config

    if not st.session_state.auth:
        login_screen()
    else:
        sidebar()
        route()

if __name__ == "__main__":
    main()
