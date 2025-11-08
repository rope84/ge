# app.py
import streamlit as st
import traceback

from core.db import setup_db
from core.auth import seed_admin_if_empty
from core import auth
from core.ui_theme import use_theme, page_header, small_footer
from login import render_login_form
from core.config import APP_NAME, APP_VERSION

def go_to_profile():
    st.session_state["nav_choice"] = "Profil"
    st.rerun()

# ---------------- Initial Setup ----------------
setup_db()
seed_admin_if_empty()

# ---------------- Dynamic Module Import (with hot reload) ----------------
import importlib, inspect, datetime
from pathlib import Path

def import_modules():
    modules, errors = {}, {}
    loaded_meta = {}  # optionales Debugging

    def try_import(qualified_name: str):
        base = qualified_name.split(".")[-1]  # z.B. "start" aus "modules.start"
        try:
            mod = importlib.import_module(qualified_name)
            mod = importlib.reload(mod)  # Hot-Reload

            fn = getattr(mod, f"render_{base}")  # erwartet z.B. render_start()
            modules[base] = fn

            file_path = Path(inspect.getfile(mod))
            loaded_meta[base] = {
                "file": str(file_path),
                "mtime": datetime.datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(sep=" ", timespec="seconds"),
                "qualified": qualified_name,
            }
        except Exception as e:
            modules[base] = None
            errors[base] = f"{type(e).__name__}: {e}\n\n" + traceback.format_exc()

    # WICHTIG: cashflow statt abrechnung laden
    for mod_name in ["start", "cashflow", "dashboard", "inventur", "profile", "admin"]:
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
            line-height: 1.4em;
            z-index: 0;                 /* liegt hinter dem Content */
            pointer-events: none;       /* blockiert keine Klicks/Eingaben */
        }}
        .footer a {{
            color: #bbb;
            text-decoration: none;
            font-weight: bold;
            pointer-events: auto;       /* Links bleiben klickbar */
        }}
        .footer a:hover {{
            color: white;
            text-decoration: underline;
        }}
        </style>

        <div class="footer">
            👤 {st.session_state.get('username', 'Gast')}<br>
            Rechte: <span style='opacity:0.8'>{st.session_state.get('role', 'guest')}</span><br>
            <span style='opacity:0.7'>{APP_NAME} {APP_VERSION}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------- Sidebar ----------------
def sidebar():
    with st.sidebar:
        # Query-Param (Footer-Link) abfangen
        query_params = st.query_params
        if "nav_choice" in query_params:
            st.session_state["nav_choice"] = query_params["nav_choice"]
            st.query_params.clear()

        # Einmal-Navigation über Flag abfangen (aus Modulen wie start.py)
        if st.session_state.get("nav_to"):
            st.session_state["nav_choice"] = st.session_state.pop("nav_to")

        # Optionaler Profil-Flag
        if st.session_state.get("go_profile"):
            st.session_state["nav_choice"] = "Profil"
            del st.session_state["go_profile"]

        # Header
        st.markdown(f"### {APP_NAME}")
        st.caption(APP_VERSION)

        # Navigation (an nav_choice gebunden)
        display_pages = ["Start", "Abrechnung", "Dashboard", "Inventur", "Profil"]
        if st.session_state.role == "admin":
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

        fixed_footer()

# ---------------- Routing ----------------
DISPLAY_TO_MODULE = {
    "start": "start",
    # Mapping: Anzeige "Abrechnung" -> Modul cashflow
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
        st.code(mod_err or "Unbekannter Fehler", language="text")
        return

    try:
        if mod_key == "start":
            mod_func(st.session_state.username or "Gast")

        elif mod_key == "cashflow":
            # Neues Abrechnungsmodul benötigt keine Parameter
            mod_func()

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
