# app.py
import traceback
import datetime
import importlib
import inspect
from pathlib import Path

import streamlit as st

from core.db import setup_db
setup_db()

from core.ui_theme import use_theme
from login import render_login_form
from core.config import APP_NAME, APP_VERSION

# ---------------- Dynamic Module Import (Hot Reload) ----------------
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
        except Exception
