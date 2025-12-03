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

st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        min-width: 250px !important;
        max-width: 250px !important;
        width: 250px !important;
        visibility: visible !important;
        display: block !important;
    }
    [data-testid="stSidebar"] button[title="Collapse sidebar"] {
        display: none;
    }
    </style>
""", unsafe_allow_html=True)

# Debug-Zeile in Sidebar erzwingen
with st.sidebar:
    st.info("✅ Sidebar geladen")
    st.markdown("<!-- Sidebar sichtbar -->")



st.markdown("""
    <style>
    section[data-testid="stSidebar"] button[title="Collapse sidebar"] {
        display: none;
    }
    </style>
""", unsafe_allow_html=True)


# ---------------- Initial Setup ----------------
setup_db()  # DB-Datei + Basis vorhanden

# ensure_admin_consistency LAZY & fehlertolerant nach DB-Setup
try:
    auth_mod = importlib.import_module("core.auth")
    if hasattr(auth_mod, "ensure_admin_consistency"):
        auth_mod.ensure_admin_consistency()
    if hasattr(auth_mod, "seed_admin_if_empty"):
        auth_mod.seed_admin_if_empty()
except Exception:
    # nicht blockieren – Details stehen im Streamlit-Log
    pass


# ---------------- Dynamic Module Import (Hot Reload) ----------------
def import_modules():
    modules, errors, loaded_meta = {}, {}, {}

    def try_import(qualified_name: str):
        base = qualified_name.split(".")[-1]
        try:
            mod = importlib.import_module(qualified_name)
            mod = importlib.reload(mod)
            fn = getattr(mod, f"render_{base}")  # z.B. render_start()
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

    # Wichtig: cashflow statt abrechnung laden
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
    st.session_state.clear()
    init_session()
    st.rerun()


def _lazy_auth():
    """core.auth erst laden, wenn wirklich gebraucht (verhindert Zyklen)."""
    return importlib.import_module("core.auth")


def login_screen():
    u, p, pressed = render_login_form(APP_NAME, APP_VERSION)
    if not pressed:
        return

    if not u or not p:
        st.error("Bitte Benutzername und Passwort eingeben.")
        return

    # Sichtbarer Mini-Diagnoseblock
    try:
        with conn() as cn:
            c = cn.cursor()
            row = c.execute(
                """
                SELECT username,
                       COALESCE(status,'active'),
                       COALESCE(functions,''),
                       LENGTH(COALESCE(passhash,'')) 
                  FROM users WHERE username=?
                """,
                (u.strip(),),
            ).fetchone()
        if row:
            st.caption(
                f"Debug · user={row[0]} · status={row[1]} · "
                f"functions={row[2]} · passhash_len={row[3]}"
            )
        else:
            st.caption("Debug · Benutzer in DB nicht gefunden.")
    except Exception as e:
        st.caption(f"Debug · DB-Check fehlgeschlagen: {e}")

    # Eigentliche Anmeldung
    try:
        auth = _lazy_auth()
        ok, role, _scope = auth._do_login(u, p)  # (ok, role, functions)
    except Exception as e:
        st.error("Login-Fehler (interner Ausnahmefehler).")
        st.exception(e)
        return

    if ok:
        if not st.session_state.get("role"):
            st.session_state["role"] = role or "user"
        st.rerun()
    else:
        st.error("❌ Login fehlgeschlagen. Prüfe Status (muss 'active' sein) und Passwort.")


# ---------------- Fixed Footer ----------------
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
            line-height: 1.4em;
            z-index: 0;
            pointer-events: none;
        }}
        .footer a {{
            color: #bbb;
            text-decoration: none;
            font-weight: bold;
            pointer-events: auto;
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

        # --- Rechte für Inventur prüfen ---
        funcs = (st.session_state.get("scope") or "").lower()
        role = (st.session_state.get("role") or "").lower()

        display_pages = ["Start", "Abrechnung", "Dashboard", "Profil"]

        if ("inventur" in funcs) or (role == "admin"):
            # Inventur vor Profil einfügen
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

        fixed_footer()

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
            with st.expander(
                f"Details zu Ladefehler '{mod_key}'", expanded=False
            ):
                st.code(mod_err, language="text")
        return

    try:
        if mod_key == "start":
            mod_func(st.session_state.username or "Gast")
        elif mod_key == "cashflow":
            mod_func()
        elif mod_key == "dashboard":
            mod_func()
        elif mod_key == "inventur":
            # Einfach Username übergeben, Rolle in Session
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

    if not st.session_state.auth:
        login_screen()
    else:
        sidebar()
        route()


if __name__ == "__main__":
    main()
