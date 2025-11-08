# modules/cashflow/utils.py
import streamlit as st
from typing import Dict, Any, Optional, List
from core.db import conn

def get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def set_meta(key: str, value: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))
        cn.commit()

def user_has_function(username: str, func_name: str) -> bool:
    """
    True wenn:
      - der eingeloggte User in users.functions die Funktion trägt (case-insensitive) ODER
      - die Session-Rolle 'admin' ist (Admin sieht alles)
    """
    # Admin-Override
    if (st.session_state.get("role") or "").strip().lower() == "admin":
        return True

    if not username:
        return False

    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT functions FROM users WHERE username=?", (username,)).fetchone()
        if not row or not row[0]:
            return False
        funcs = [f.strip().lower() for f in row[0].split(",") if f.strip()]
        return func_name.strip().lower() in funcs

# Zählwerte aus meta lesen (Bars/Kassen/Garderoben)
_META_KEYS = {
    "bars": ["bars_count", "business_bars", "num_bars"],
    "registers": ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

def numbers_from_meta() -> Dict[str, int]:
    def _first_int(keys: List[str], dflt: int = 0) -> int:
        for k in keys:
            v = get_meta(k)
            if v is not None and str(v).strip() != "":
                try:
                    return max(0, int(float(str(v).strip())))
                except Exception:
                    continue
        return dflt

    return {
        "bars": _first_int(_META_KEYS["bars"], 0),
        "registers": _first_int(_META_KEYS["registers"], 0),
        "cloakrooms": _first_int(_META_KEYS["cloakrooms"], 0),
    }
