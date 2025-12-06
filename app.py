
# app_topbar_buttons.py

import traceback
import importlib
import streamlit as st
from core.db import setup_db, conn
from core.ui_theme import use_theme
from core.config import APP_NAME, APP_VERSION

setup_db()

try:
    auth_mod = importlib.import_module("core.auth")
    if hasattr(auth_mod, "ensure_admin_consistency"):
        auth_mod.ensure_admin_consistency()
    if hasattr(auth_mod, "seed_admin_if_empty"):
        auth_mod.seed_admin_if_empty()
except Exception as e:
    print("[WARNUNG] Auth-Initialisierung fehlgeschlagen:", e)

def is_setup_done() -> bool:
    try:
        with conn() as c:
            row = c.execute("SELECT value FROM setup WHERE key='setup_done'").fetchone()
            return row and row[0].lower() == "yes"
    except Exception:
        return False

def import_modules():
    modules, errors, loaded_meta = {}, {}, {}
    def try_import(qualified_name: str):
        base = qualified_name.split(".")[-1]
        try:
            mod = importlib.import_module(qualified_name)
            mod = importlib.reload(mod)
            fn = getattr(mod, f"render_{base}")
            modules[base] = fn
        except Exception as e:
            modules[base] = None
            errors[base] = f"{type(e).__name__}: {e}\n\n" + traceback.format_exc()
    for mod_name in ["start", "cashflow", "dashboard", "inventur", "profile", "admin", "setup"]:
        try_import(f"modules.{mod_name}")
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

def _lazy_auth():
    return importlib.import_module("core.auth")

def login_screen():
    from login import render_login_form
    u, p, pressed = render_login_form(APP_NAME, APP_VERSION)
    if not pressed:
        return
    if not u or not p:
        st.error("Bitte Benutzername und Passwort eingeben.")
        return
    try:
        auth = _lazy_auth()
        ok, role, scope = auth._do_login(u, p)
    except Exception as e:
        st.error("Login-Fehler.")
        st.exception(e)
        return
    if ok:
        st.session_state["auth"] = True
        st.session_state["username"] = u
        st.session_state["role"] = role or "user"
        st.session_state["scope"] = scope or ""
        st.rerun()
    else:
        st.error("❌ Login fehlgeschlagen. Prüfe Benutzername, Passwort und Status.")

DISPLAY_TO_MODULE = {
    "start": "start",
    "abrechnung": "cashflow",
    "dashboard": "dashboard",
    "inventur": "inventur",
    "profil": "profile",
    "admin-cockpit": "admin",
}

def topbar_buttons():
    if not st.session_state.get("auth"):
        return

    st.markdown(f"<h3 style='margin-bottom: 0;'>{APP_NAME}</h3>", unsafe_allow_html=True)

    role = st.session_state.get("role", "user").lower()
    funcs = st.session_state.get("scope", "").lower()

    pages = ["Start", "Abrechnung", "Dashboard", "Profil"]
    if "inventur" in funcs or role == "admin":
        pages.insert(3, "Inventur")
    if role == "admin":
        pages.append("Admin-Cockpit")

    cols = st.columns([len(pages)] + [1] * (len(pages) - 1) + [3, 1])
    for i, page in enumerate(pages):
        if cols[i].button(page, use_container_width=True):
            st.session_state["nav_choice"] = page

    with cols[-2]:
        st.caption(f"👤 {st.session_state['username']} ({st.session_state['role']})")
    with cols[-1]:
        if st.button("Logout"):
            logout()

    st.markdown("---")

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

def main():
    st.set_page_config(page_title=APP_NAME, page_icon="🍸", layout="wide")
    st.markdown('<style>.block-container { padding-top: 1rem; }</style>', unsafe_allow_html=True)
    use_theme()

    if not is_setup_done():
        modules["setup"]()
    elif not st.session_state.get("auth"):
        login_screen()
    else:
        topbar_buttons()
        route()

if __name__ == "__main__":
    main()
