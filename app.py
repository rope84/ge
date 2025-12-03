import traceback
import datetime
import importlib
import inspect
import streamlit as st
from pathlib import Path

from core.db import setup_db, conn
from core.ui_theme import use_theme
from login import render_login_form
from core.config import APP_NAME, APP_VERSION

# Datenbank vorbereiten
setup_db()

def setup_completed() -> bool:
    try:
        with conn() as c:
            row = c.execute("SELECT value FROM setup WHERE key='setup_done'").fetchone()
            return bool(row and row[0].lower() == "yes")
    except:
        return False

def render_setup():
    mod = importlib.import_module("modules.setup")
    mod.render_setup()

def import_modules():
    modules, errors, loaded_meta = {}, {}, {}
    for mod_name in ["start", "cashflow", "dashboard", "inventur", "profile", "admin"]:
        try:
            mod = importlib.import_module(f"modules.{mod_name}")
            mod = importlib.reload(mod)
            fn = getattr(mod, f"render_{mod_name}", None)
            modules[mod_name] = fn
        except Exception as e:
            modules[mod_name] = None
            errors[mod_name] = f"{type(e).__name__}: {e}\n\n" + traceback.format_exc()
    return modules, errors

modules, import_errors = import_modules()

def init_session():
    s = st.session_state
    s.setdefault("auth", False)
    s.setdefault("username", "")
    s.setdefault("functions", "")
    s.setdefault("nav_choice", "Start")

init_session()

def logout():
    st.session_state.clear()
    init_session()
    st.rerun()

def login_screen():
    u, p, pressed = render_login_form(APP_NAME, APP_VERSION)
    if not pressed:
        return
    if not u or not p:
        st.error("Bitte Benutzername und Passwort eingeben.")
        return

    try:
        auth = importlib.import_module("core.auth")
        ok, role, _ = auth._do_login(u, p)
    except Exception as e:
        st.error("Login-Fehler")
        st.exception(e)
        return

    if ok:
        st.session_state["auth"] = True
        st.session_state["username"] = u
        st.session_state["functions"] = role
        st.rerun()
    else:
        st.error("Login fehlgeschlagen. Benutzername oder Passwort falsch.")

def fixed_footer():
    st.markdown(
        f"""
        <style>
        .footer {{
            position: fixed;
            bottom: 10px;
            left: 12px;
            font-size: 12px;
            color: gray;
            opacity: 0.85;
        }}
        </style>
        <div class="footer">
            👤 {st.session_state.get('username', 'Gast')}<br>
            Rechte: {st.session_state.get('functions', '—')}<br>
            {APP_NAME} {APP_VERSION}
        </div>
        """,
        unsafe_allow_html=True,
    )

def sidebar():
    if not st.session_state.get("auth"):
        return
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(APP_VERSION)

        pages = ["Start", "Abrechnung", "Dashboard", "Profil"]
        if "inventur" in st.session_state.get("functions", ""):
            pages.append("Inventur")
        if st.session_state.get("functions") == "admin":
            pages.append("Admin-Cockpit")

        st.radio("Navigation", pages, key="nav_choice", label_visibility="collapsed")
        st.divider()
        if st.button("Logout", use_container_width=True):
            logout()
        fixed_footer()

def route():
    page = st.session_state.get("nav_choice", "start").lower()
    key = {"abrechnung": "cashflow", "admin-cockpit": "admin"}.get(page, page)
    func = modules.get(key)
    if func:
        func()
    else:
        st.error(f"Modul '{key}' fehlt")

def main():
    st.set_page_config(page_title=APP_NAME, page_icon="🍸", layout="wide")
    use_theme()

    if not setup_completed():
        render_setup()
    elif not st.session_state.auth:
        login_screen()
    else:
        sidebar()
        route()

if __name__ == "__main__":
    main()
