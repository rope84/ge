# modules/cashflow/utils.py
from typing import Optional, Dict, List
from core.db import conn

META_KEYS = {
    "bars": ["bars_count", "business_bars", "num_bars"],
    "registers": ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def global_unit_caps() -> Dict[str, int]:
    def _first_int(keys: List[str], dflt: int = 0) -> int:
        for k in keys:
            v = _get_meta(k)
            if v is not None and str(v).strip() != "":
                try:
                    return max(0, int(float(str(v).strip())))
                except Exception:
                    continue
        return dflt
    return {
        "bars": _first_int(META_KEYS["bars"], 0),
        "registers": _first_int(META_KEYS["registers"], 0),
        "cloakrooms": _first_int(META_KEYS["cloakrooms"], 0),
    }

def user_has_function(username: str, func_name: str) -> bool:
    if not username:
        return False
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT functions FROM users WHERE username=?", (username,)).fetchone()
    if not r or r[0] is None:
        return False
    funcs = [f.strip().lower() for f in r[0].split(",") if f.strip()]
    return func_name.lower() in funcs
