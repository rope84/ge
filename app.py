import traceback
import importlib
import streamlit as st
from core.db import setup_db, conn
from core.ui_theme import use_theme
from core.config import APP_NAME, APP_VERSION

# initialize DB and theme
setup_db()
use_theme()

# ensure admin seed/consistency if available
try:
    auth_mod = importlib.import_module("core.auth")
    if hasattr(auth_mod, "ensure_admin_consistency"):
        auth_mod.ensure_admin_consistency()
    if hasattr(auth_mod, "seed_admin_if_empty"):
        auth_mod.seed_admin_if_empty()
except Exception as e:
    st.write("[WARNUNG] Auth-Initialisierung fehlgeschlagen:", e)


def is_setup_done() -> bool:
    try:
        with conn() as c:
            row = c.execute("SELECT value FROM setup WHERE key='setup_done'").fetchone()
            return bool(row and (row[0] or "").lower() == "yes")
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


def sidebar_with_icons():
    if not st.session_state.get("auth"):
        return

    # simple navigation sidebar
    with st.sidebar:
        st.markdown("### Navigation")
        choice = st.radio("", ["Start", "Dashboard", "Abrechnung", "Inventur", "Profil", "Admin-Cockpit"])
        st.session_state["nav_choice"] = choice
        st.write("---")
        st.button("Logout", on_click=logout)


# Main rendering logic
def main():
    st.title(APP_NAME)

    # show setup if not done
    if not is_setup_done():
        # render setup module if available
        fn = modules.get("setup")
        if fn:
            try:
                fn()
            except Exception as e:
                st.error("Fehler im Setup-Modul")
                st.exception(e)
        else:
            st.error("Setup-Modul nicht verfügbar. Siehe Logs.")
        return

    # not authenticated -> show login
    if not st.session_state.get("auth"):
        login_screen()
        return

    # authenticated -> show sidebar and selected module
    sidebar_with_icons()
    sel = st.session_state.get("nav_choice", "Start")
    module_key = DISPLAY_TO_MODULE.get(sel.lower(), "start") if isinstance(sel, str) else "start"
    fn = modules.get(module_key)
    if fn:
        try:
            fn()
        except Exception as e:
            st.error("Fehler beim Laden des Moduls.")
            st.exception(e)
    else:
        st.error(f"Modul '{module_key}' konnte nicht geladen werden.")
        if import_errors.get(module_key):
            st.text(import_errors.get(module_key))


if __name__ == "__main__":
    main()
