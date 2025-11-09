# app.py
import streamlit as st
import traceback
import importlib, inspect, datetime
from pathlib import Path

from core.db import setup_db
from core.auth import seed_admin_if_empty  # <- nur seed importieren
from core import auth                      # <- ganzes Modul, damit wir später optional callen
from core.ui_theme import use_theme
from login import render_login_form
from core.config import APP_NAME, APP_VERSION

# ---------------- Initial Setup ----------------
setup_db()
seed_admin_if_empty()

# Admin-Konsistenz erst NACH dem DB-Setup sicher & fehlertolerant prüfen
try:
    # Achtung: jetzt existiert die DB sicher
    if hasattr(auth, "ensure_admin_consistency"):
        auth.ensure_admin_consistency()
except Exception:
    # Leise überspringen; Details stehen in den Streamlit-Logs
    pass
# NEU: Import der Sicherung
from core.auth import ensure_admin_consistency

# ---------------- Initial Setup ----------------
setup_db()
seed_admin_if_empty()
# NEU: Admin-Konsistenz sicherstellen (ohne Admin-UI)
ensure_admin_consistency()
# ---------------- Initial Setup ----------------
setup_db()
seed_admin_if_empty()

# Versuche optional Admin-Konsistenz herzustellen, ohne App-Start zu blockieren
try:
    from core import auth as _authmod
    # kleine, sichere Migration: Spalte 'status' anlegen, falls sie fehlt
    try:
        from core.db import conn
        with conn() as _cn:
            _c = _cn.cursor()
            cols = {r[1] for r in _c.execute("PRAGMA table_info(users)").fetchall()}
            if "status" not in cols:
                _c.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'")
                _cn.commit()
    except Exception:
        pass

    if hasattr(_authmod, "ensure_admin_consistency"):
        _authmod.ensure_admin_consistency()
except Exception:
    # leise überspringen; Details stehen in den Streamlit-Logs
    pass
# ---------------- Dynamic Module Import (mit Hot Reload) ----------------
def import_modules():
    modules, errors, loaded_meta = {}, {}, {}

    def try_import(qualified_name: str):
        base = qualified_name.split(".")[-1]
        try:
            mod = importlib.import_module(qualified_name)
            mod = importlib.reload(mod)
            fn = getattr(mod, f"render_{base}")  # z. B. render_start()
            modules[base] = fn

            file_path = Path(inspect.getfile(mod))
            loaded_meta[base] = {
                "file": str(file_path),
                "mtime": datetime.datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(
                    sep=" ", timespec="seconds"
                ),
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
    # robuster & kürzer
    st.session_state.clear()
    init_session()
    st.rerun()

def login_screen():
    u, p, pressed = render_login_form(APP_NAME, APP_VERSION)
    if pressed:
        if not u or not p:
            st.error("Bitte Benutzername und Passwort eingeben.")
            return

        # --- Sichtbares Debug: Zeig den DB-Zustand dieses Users an
        try:
            from core.db import conn
            with conn() as cn:
                c = cn.cursor()
                row = c.execute(
                    "SELECT username, COALESCE(status,'active') AS status, "
                    "COALESCE(functions,'') AS functions, LENGTH(COALESCE(passhash,'')) AS pass_len "
                    "FROM users WHERE username=?",
                    (u.strip(),)
                ).fetchone()
            if row:
                st.caption(f"Debug · user={row[0]} · status={row[1]} · functions={row[2]} · passhash_len={row[3]}")
            else:
                st.caption("Debug · Benutzer in DB nicht gefunden.")
        except Exception as e:
            st.caption(f"Debug · DB-Check fehlgeschlagen: {e}")

        # --- Eigentlicher Login
        try:
            ok_role_tuple = getattr(auth, "_do_login")(u, p)  # (ok, role, functions)
            ok = bool(ok_role_tuple[0])
        except Exception as e:
            st.error("Login-Fehler (interner Ausnahmefehler).")
            # Wichtig: temporär sichtbar machen, dann wieder entfernen
            st.exception(e)
            return

        if ok:
            if not st.session_state.get("role"):
                st.session_state["role"] = "user"
            st.rerun()
        else:
            # Häufigste Ursachen: status != active, Passwort falsch
            # Wir differenzieren das hier grob anhand des DB-Zustands oben.
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
            text-decoration: underline.
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
    # Guard: Sidebar nur im eingeloggten Zustand rendern
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
        # Dynamische Aufrufe nach Modul
        if mod_key == "start":
            mod_func(st.session_state.username or "Gast")

        elif mod_key == "cashflow":
            # ohne Argumente aufrufen (neues Paket-Interface)
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
    use_theme()

    if not st.session_state.auth:
        login_screen()
    else:
        sidebar()
        route()

if __name__ == "__main__":
    main()
