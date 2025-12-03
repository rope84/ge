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

# ------------------------------------------------------
# ✅ Datenbank vorbereiten
# ------------------------------------------------------
setup_db()
db_path = Path("gastro.db").resolve()
print(f"📦 Verwendete SQLite-Datei: {db_path}")

# ------------------------------------------------------
# ✅ Setup prüfen
# ------------------------------------------------------
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
    return modules, errors, loaded_meta

modules, import_errors, import_meta = import_modules()

def init_session():
    s = st.session_state
    s.setdefault("auth", False)
    s.setdefault("username", "")
    s.setdefault("role", "guest")
    s.setdefault("scope", "")
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
        ok, role, scope = auth._do_login(u, p)
    except Exception as e:
        st.error("Login-Fehler.")
        st.exception(e)
        return
    if ok:
        st.session_state.auth = True
        st.session_state.username = u
        st.session_state.role = role or "user"
        st.session_state.scope = scope or ""
        st.rerun()
    else:
        st.error("❌ Login fehlgeschlagen.")

def fixed_footer():
    st.markdown(
        f"""
        <style>
        .footer {{
            position: fixed;
            bottom: 10px;
            left: 12px;
            width: 240px;
            text-align: left;
            font-size: 12px;
            color: gray;
            opacity: 0.85;
            z-index: 0;
            pointer-events: none;
        }}
        </style>
        <div class="footer">
            👤 {st.session_state.get('username', 'Gast')}<br>
            Rolle: {st.session_state.get('role', 'guest')}<br>
            <span style='opacity:0.7'>{APP_NAME} {APP_VERSION}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

def sidebar():
    if not st.session_state.auth:
        return
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(APP_VERSION)

        funcs = (st.session_state.get("scope") or "").lower()
        role = (st.session_state.get("role") or "").lower()

        display_pages = ["Start", "Abrechnung", "Dashboard", "Profil"]
        if "inventur" in funcs or role == "admin":
            display_pages.insert(3, "Inventur")
        if role == "admin":
            display_pages.append("Admin-Cockpit")

        st.radio(
            "Navigation",
            display_pages,
            index=display_pages.index(st.session_state.get("nav_choice", "Start")),
            label_visibility="collapsed",
            key="nav_choice",
        )
        st.divider()
        if st.button("Logout", use_container_width=True):
            logout()
        fixed_footer()

def route():
    DISPLAY_TO_MODULE = {
        "start": "start",
        "abrechnung": "cashflow",
        "dashboard": "dashboard",
        "inventur": "inventur",
        "profil": "profile",
        "admin-cockpit": "admin"
    }
    display_key = (st.session_state.get("nav_choice") or "Start").lower()
    mod_key = DISPLAY_TO_MODULE.get(display_key)
    mod_func = modules.get(mod_key)
    if not mod_func:
        st.error(f"❌ Modul nicht gefunden: {mod_key}")
        return
    try:
        if mod_key in ["start", "inventur", "profile"]:
            mod_func(st.session_state.username)
        elif mod_key == "admin":
            if st.session_state.role != "admin":
                st.error("Adminrechte erforderlich.")
            else:
                mod_func()
        else:
            mod_func()
    except Exception:
        st.error(f"❌ Laufzeitfehler in '{mod_key}'")
        st.code(traceback.format_exc())

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
