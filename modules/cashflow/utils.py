# modules/cashflow/utils.py
from typing import Dict, List, Optional, Tuple
from core.db import conn

def decode_units(units: str) -> Dict[str, List[int]]:
    out = {"bar": [], "cash": [], "cloak": []}
    if not units:
        return out
    for token in [t.strip() for t in units.split(",") if t.strip()]:
        if ":" not in token:
            continue
        t, v = token.split(":", 1)
        try:
            n = int(v)
        except Exception:
            continue
        if t in out and n not in out[t]:
            out[t].append(n)
    for k in out:
        out[k] = sorted(out[k])
    return out

def get_user(username: str) -> Optional[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id,username,functions,units FROM users WHERE username=?",
            (username,)
        ).fetchone()

def user_has_function(username: str, fn_name: str) -> bool:
    row = get_user(username or "")
    if not row:
        return False
    _, _, functions, _ = row
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    return (fn_name or "").strip().lower() in funcs or ("admin" in funcs)

def is_manager(username: str, session_role: str = "") -> bool:
    row = get_user(username or "")
    if not row:
        return session_role.lower() == "admin"
    _, _, functions, _ = row
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    return ("admin" in funcs) or ("betriebsleiter" in funcs) or (session_role.lower() == "admin")

def allowed_unit_numbers(username: str) -> Dict[str, List[int]]:
    row = get_user(username or "")
    if not row:
        return {"bar": [], "cash": [], "cloak": []}
    _, _, _, units = row
    return decode_units(units or "")
