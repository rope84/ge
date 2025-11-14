# login.py
import streamlit as st
from typing import Tuple
import importlib


def _lazy_auth():
    """Lädt core.auth nur bei Bedarf (verhindert Import-Zirkus)."""
    try:
        from core import auth as _a
        return _a
    except Exception:
        return importlib.import_module("core.auth")


def render_login_form(app_name: str, app_version: str) -> Tuple[str, str, bool]:
    """
    Zeichnet die Login-Card.
    Rückgabe: (username, password, pressed_login)
    Registrierung wird intern behandelt (Message-Feedback), beeinflusst Rückgabe nicht.
    """

    st.markdown(
        """
        <style>
        /* Sidebar auf Login-Seite ausblenden */
        [data-testid="stSidebar"] { display: none !important; }

        /* Hintergrund */
        body {
            background: radial-gradient(900px 500px at 20% -10%, #1e1b4b33, transparent),
                        radial-gradient(900px 500px at 120% 0%, #0f766e33, transparent),
                        #0b0b12;
        }

        /* --------- NERVIGE PILLE ÜBERDECKEN ---------
           Wir legen über den oberen Bereich von section.main
           einen dunklen Layer, der alles darunter „unsichtbar“ macht. */
        section.main {
            position: relative;
        }
        section.main::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 120px;          /* Höhe des überdeckten Bereichs */
            background: #050509;    /* gleiches/dunkleres Background */
            z-index: 2;
        }
        .ge-card {
            position: relative;
            z-index: 3;             /* über dem Overlay */
        }

        /* Login-Card schmäler & zentriert */
