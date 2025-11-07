# modules/cashflow/utils.py
import json
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
    if not username:
        return False
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT functions FROM users WHERE username=?", (username,)).fetchone()
        if not row or not row[0]:
            return False
        funcs = [f.strip().lower() for f in row[0].split(",") if f.strip()]
        return func_name.strip().lower() in funcs

def numbers_from_meta() -> Dict[str,int]:
    # erwartet Keys: num_bars, num_kassen, num_cloak
    def to_int(x: Optional[str]) -> int:
        try: return int(x or "0")
        except: return 0
    return {
        "bars":   to_int(get_meta("num_bars")),
        "kassen": to_int(get_meta("num_kassen")),
        "cloak":  to_int(get_meta("num_cloak")),
    }

def nice_unit_name(unit_type: str, idx: int) -> str:
    if unit_type == "bar": return f"Bar {idx}"
    if unit_type == "kassa": return f"Kassa {idx}"
    if unit_type == "cloak": return f"Garderobe {idx}"
    return f"{unit_type} {idx}"
