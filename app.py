# app.py
import traceback
import datetime
import importlib
import inspect
from pathlib import Path

import streamlit as st

from core.db import setup_db, conn
from core.ui_theme import use_theme
from login import render_login_form
from core.config import APP_NAME, APP_VERSION

# ---------------- Initial Setup ----------------
setup_db()

# ---------------- Setup-Check persistiert ----------------
def is_setup_complete():
    try:
        with conn() as c:
            row = c.execute("SELECT value FROM setup WHERE key = 'setup_done'").fetchone()
            return row and row[0] == "yes"
    except Exception:
        return False

# ---------------- Dynamic Module Import ----------------
def import_modules():
    modules, errors, loaded_meta = {}, {}, {}

    def try_import(qualified_name: str):
        base = qualified_name.split(".")[-1]
        try:
            mod = importlib.import_module(qualified_name)
            mod = importlib.reload(mod)
            fn = getattr(mod, f"render_{base}")
            modules[base] = fn

            file_path = Path(inspect.getfile(mod))
            loaded_meta[base] = {
                "file": str(file_path),
                "mtime": datetime.datetime.fromtimestamp(
                    file_path.stat().st_mtime
                ).isoformat(sep=" ", timespec="seconds"),
                "qualified": qualified_name,
            }
        except Exception as e:
            modules[base] = None
            errors[base] = f"{type(e).__name__}: {e}\n\n" + traceback.format_exc()

    for mod_name in ["start", "cashflow", "dashboard", "inventur", "profile", "admin", "setup"]:
        try_import(f"modules.{mod_name}")

    return modules, errors, loaded_meta

modules, import_errors, import_meta = import_modules()

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
    st.session_state.clear()
    init_session()
    st.rerun()

def _lazy_auth():
    return importlib.import_module("core.auth")

def login_screen():
    u, p, pressed = render_login_form(APP_NAME, APP_VERSION)
    if not pressed:
        return

    if not u or not p:
        st.error("Bitte Benutzername und Passwort eingeben.")
        return

    try:
        auth = _lazy_auth()
        ok, role, _scope = auth._do_login(u, p)
    except Exception as e:
        st.error("Login-Fehler (interner Ausnahmefehler).")
        st.exception(e)
        return

    if ok:
        st.session_state["role"] = role or "user"
        st.session_state["auth"] = True
        st.session_state["username"] = u
        st.rerun()
    else:
        st.error("❌ Login fehlgeschlagen. Prüfe Status und Passwort.")

# ---------------- Sidebar ----------------
def sidebar():
    if not st.session_state.get("auth"):
        return

    with st.sidebar:
        query_params = st.query_params
        if "nav_choice" in query_params:
            st.session_state["nav_choice"] = query_params["nav_choice"]
            st.query_params.clear()

        if st.session_state.get("nav_to"):
            st.session_state["nav_choice"] = st.session_state.pop("nav_to")

        if st.session_state.get("go_profile"):
            st.session_state["nav_choice"] = "Profil"
            del st.session_state["go_profile"]

        st.markdown(f"### {APP_NAME}")
        st.caption(APP_VERSION)

        funcs = (st.session_state.get("scope") or "").lower()
        role = (st.session_state.get("role") or "").lower()

        display_pages = ["Start", "Abrechnung", "Dashboard", "Profil"]

        if ("inventur" in funcs) or (role == "admin"):
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
        if st.session_state.auth and st.button("Logout", use_container_width=True):
            logout()

# ---------------- Routing ----------------
DISPLAY_TO_MODULE = {
    "start": "start",
    "abrechnung": "cashflow",
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
        if mod_err:
            with st.expander(f"Details zu Ladefehler '{mod_key}'", expanded=False):
                st.code(mod_err, language="text")
        return

    try:
        if mod_key == "start":
            mod_func(st.session_state.username or "Gast")
        elif mod_key in ["cashflow", "dashboard"]:
            mod_func()
        elif mod_key == "inventur":
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
    use_theme()

    if not is_setup_complete():
        import modules.setup as setup
        setup.render_setup()
        return

    if not st.session_state.auth:
        login_screen()
    else:
        sidebar()
        route()

if __name__ == "__main__":
    main()
