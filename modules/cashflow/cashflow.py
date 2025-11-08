# modules/cashflow.py
import streamlit as st
import datetime
from typing import Dict, List, Tuple, Optional
from core.db import conn

# -----------------------------
# Utilities & Rights
# -----------------------------

def _decode_units(units: str) -> Dict[str, List[int]]:
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

def _get_user(func_username: str) -> Optional[tuple]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT id, username, functions, units FROM users WHERE username=?",
            (func_username,),
        ).fetchone()
        return row

def _user_rights(username: str, session_role: str = "") -> Dict:
    row = _get_user(username)
    if not row:
        return {"is_admin_manager": session_role.lower() == "admin",
                "units": {"bar": [], "cash": [], "cloak": []}}
    _, _, functions, units = row
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    is_admin_manager = ("admin" in funcs) or ("betriebsleiter" in funcs) or (session_role.lower() == "admin")
    allowed = _decode_units(units or "")
    return {"is_admin_manager": is_admin_manager, "units": allowed}

# -----------------------------
# Meta: Unit Counts & Prices
# -----------------------------

_META_UNIT_KEYS = {
    "bars": ["bars_count", "business_bars", "num_bars"],
    "registers": ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

def _get_counts() -> Dict[str, int]:
    def _first_int(keys: List[str], default: int = 0) -> int:
        for k in keys:
            v = _get_meta(k)
            if v is not None and str(v).strip() != "":
                try:
                    return max(0, int(float(str(v).strip())))
                except Exception:
                    continue
        return default

    return {
        "bars": _first_int(_META_UNIT_KEYS["bars"], 0),
        "registers": _first_int(_META_UNIT_KEYS["registers"], 0),
        "cloakrooms": _first_int(_META_UNIT_KEYS["cloakrooms"], 0),
    }

def _get_prices() -> Tuple[float, float]:
    def _f(name: str, dflt: float) -> float:
        v = _get_meta(name)
        try:
            return float(str(v).replace(",", ".")) if v is not None else dflt
        except Exception:
            return dflt
    return _f("conf_coat_price", 2.0), _f("conf_bag_price", 3.0)

# -----------------------------
# DB Schema (events, items, audit)
# -----------------------------

def _ensure_tables():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',  -- open | approved | closed
                created_by TEXT,
                created_at TEXT,
                approved_by TEXT,
                approved_at TEXT
            )
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name
            ON events(event_date, name)
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                unit_type TEXT NOT NULL,             -- bar|cash|cloak
                unit_no INTEGER NOT NULL,
                field TEXT NOT NULL,                  -- cash,pos1,pos2,pos3,voucher,tables/card/coats_eur/bags_eur
                value REAL NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TEXT,
                UNIQUE(event_id, unit_type, unit_no, field)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                user TEXT,
                action TEXT,
                details TEXT
            )
        """)
        cn.commit()

def _audit(user: str, action: str, details: str):
    with conn() as cn:
        c = cn.cursor()
        c.execute(
            "INSERT INTO audit_log(ts, user, action, details) VALUES(?,?,?,?)",
            (datetime.datetime.now().isoformat(timespec="seconds"), user, action, details),
        )
        cn.commit()

# -----------------------------
# Event lifecycle
# -----------------------------

def _get_or_create_event(day: datetime.date, name: str, username: str) -> int:
    day_str = day.isoformat()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT id FROM events WHERE event_date=? AND name=?",
            (day_str, name.strip()),
        ).fetchone()
        if row:
            return row[0]
        c.execute(
            "INSERT INTO events(event_date, name, status, created_by, created_at) VALUES(?,?,?,?,?)",
            (day_str, name.strip(), "open", username, datetime.datetime.now().isoformat(timespec="seconds")),
        )
        cn.commit()
        ev_id = c.lastrowid
    _audit(username, "event_create", f"{day_str} | {name}")
    return ev_id

def _get_event(event_id: int) -> Optional[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, event_date, name, status, created_by, created_at, approved_by, approved_at "
            "FROM events WHERE id=?", (event_id,)
        ).fetchone()

def _set_event_status(event_id: int, status: str, username: str):
    with conn() as cn:
        c = cn.cursor()
        if status == "approved":
            c.execute(
                "UPDATE events SET status=?, approved_by=?, approved_at=? WHERE id=?",
                (status, username, datetime.datetime.now().isoformat(timespec="seconds"), event_id),
            )
        else:
            c.execute("UPDATE events SET status=? WHERE id=?", (status, event_id))
        cn.commit()
    _audit(username, "event_status", f"{event_id} -> {status}")

# -----------------------------
# Load/Save values
# -----------------------------

BAR_FIELDS = ["cash", "pos1", "pos2", "pos3", "voucher", "tables"]
CASH_FIELDS = ["cash", "card"]
CLOAK_FIELDS = ["coats_eur", "bags_eur"]

def _load_unit_values(event_id: int, unit_type: str, unit_no: int) -> Dict[str, float]:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT field, value FROM cashflow_item
            WHERE event_id=? AND unit_type=? AND unit_no=?
        """, (event_id, unit_type, unit_no)).fetchall()
    out = {f: 0.0 for f in (BAR_FIELDS if unit_type=="bar" else CASH_FIELDS if unit_type=="cash" else CLOAK_FIELDS)}
    for f, v in rows:
        try:
            out[f] = float(v)
        except Exception:
            pass
    return out

def _save_unit_values(event_id: int, unit_type: str, unit_no: int, data: Dict[str, float], username: str):
    with conn() as cn:
        c = cn.cursor()
        for k, v in data.items():
            c.execute("""
                INSERT INTO cashflow_item(event_id, unit_type, unit_no, field, value, updated_by, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(event_id, unit_type, unit_no, field)
                DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, updated_at=excluded.updated_at
            """, (event_id, unit_type, unit_no, k, float(v or 0.0), username, datetime.datetime.now().isoformat(timespec="seconds")))
        cn.commit()
    _audit(username, "unit_save", f"{event_id} {unit_type}#{unit_no} -> {data}")

# -----------------------------
# UI Bits
# -----------------------------

def _tile(title: str, subtitle: str, key: str) -> bool:
    with st.container(border=True):
        st.markdown(f"**{title}**  \n"
                    f"<span style='opacity:.7;font-size:12px'>{subtitle}</span>",
                    unsafe_allow_html=True)
        return st.button("Öffnen", key=key, use_container_width=True)

def _unit_overview(event_id: int, username: str, rights: Dict, counts: Dict[str, int]):
    st.subheader("Einheiten")
    if counts["bars"] + counts["registers"] + counts["cloakrooms"] == 0:
        st.info("Keine Einheiten (Bars/Kassen/Garderobe) konfiguriert – bitte im Admin-Bereich unter „Betrieb“ festlegen.")
        return

    is_mgr = rights["is_admin_manager"]
    allowed = rights["units"]

    def _visible(unit_type: str, i: int) -> bool:
        return True if is_mgr else (i in allowed.get(unit_type, []))

    # Bars
    if counts["bars"]:
        st.caption("Bars")
        cols = st.columns(min(4, max(1, counts["bars"])))
        ci = 0
        for i in range(1, counts["bars"]+1):
            if not _visible("bar", i):
                continue
            if _tile(f"Bar {i}", "Umsatz & Voucher erfassen", key=f"open_bar_{event_id}_{i}"):
                st.session_state["cf_unit"] = ("bar", i)
                st.rerun()
            ci = (ci + 1) % len(cols)

    # Kassen
    if counts["registers"]:
        st.caption("Kassen")
        cols = st.columns(min(4, max(1, counts["registers"])))
        ci = 0
        for i in range(1, counts["registers"]+1):
            if not _visible("cash", i):
                continue
            if _tile(f"Kassa {i}", "Bar/Unbar (Karten) erfassen", key=f"open_cash_{event_id}_{i}"):
                st.session_state["cf_unit"] = ("cash", i)
                st.rerun()
            ci = (ci + 1) % len(cols)

    # Garderoben
    if counts["cloakrooms"]:
        st.caption("Garderoben")
        cols = st.columns(min(4, max(1, counts["cloakrooms"])))
        ci = 0
        for i in range(1, counts["cloakrooms"]+1):
            if not _visible("cloak", i):
                continue
            if _tile(f"Garderobe {i}", "Jacken/Taschen erfassen", key=f"open_cloak_{event_id}_{i}"):
                st.session_state["cf_unit"] = ("cloak", i)
                st.rerun()
            ci = (ci + 1) % len(cols)

def _unit_editor(event_id: int, unit_type: str, unit_no: int, username: str, locked: bool = False):
    st.markdown(f"#### {unit_type.upper()} #{unit_no}")
    vals = _load_unit_values(event_id, unit_type, unit_no)

    if unit_type == "bar":
        c1,c2,c3,c4 = st.columns(4)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), disabled=locked, key=f"v_cash_{unit_type}_{event_id}_{unit_no}")
        pos1 = c2.number_input("Bankomat 1 (€)", min_value=0.0, step=50.0, value=float(vals["pos1"]), disabled=locked, key=f"v_pos1_{unit_type}_{event_id}_{unit_no}")
        pos2 = c3.number_input("Bankomat 2 (€)", min_value=0.0, step=50.0, value=float(vals["pos2"]), disabled=locked, key=f"v_pos2_{unit_type}_{event_id}_{unit_no}")
        pos3 = c4.number_input("Bankomat 3 (€)", min_value=0.0, step=50.0, value=float(vals["pos3"]), disabled=locked, key=f"v_pos3_{unit_type}_{event_id}_{unit_no}")
        v1, v2 = st.columns([2,1])
        voucher = v1.number_input("Voucher (€)", min_value=0.0, step=10.0, value=float(vals["voucher"]), disabled=locked, key=f"v_voucher_{unit_type}_{event_id}_{unit_no}")
        tables = v2.number_input("Tische (Stk)", min_value=0, step=1, value=int(vals["tables"]), disabled=locked, key=f"v_tables_{unit_type}_{event_id}_{unit_no}")
        total = float(cash)+float(pos1)+float(pos2)+float(pos3)+float(voucher)
        st.info(f"Umsatz gesamt: **{total:,.2f} €**", icon="💶")
        payload = {"cash": cash, "pos1": pos1, "pos2": pos2, "pos3": pos3, "voucher": voucher, "tables": tables}

    elif unit_type == "cash":
        c1,c2 = st.columns(2)
        cash = c1.number_input("Barumsatz (€)", min_value=0.0, step=50.0, value=float(vals["cash"]), disabled=locked, key=f"v_cash_{unit_type}_{event_id}_{unit_no}")
        card = c2.number_input("Unbar / Karte (€)", min_value=0.0, step=50.0, value=float(vals["card"]), disabled=locked, key=f"v_card_{unit_type}_{event_id}_{unit_no}")
        st.info(f"Kassa gesamt: **{(cash+card):,.2f} €**", icon="🧾")
        payload = {"cash": cash, "card": card}

    else:  # cloak
        coat_p, bag_p = _get_prices()
        c1,c2 = st.columns(2)
        coats_eur = c1.number_input(f"Jacken/Kleidung (€) – Stückpreis {coat_p:.2f} €", min_value=0.0, step=10.0, value=float(vals["coats_eur"]), disabled=locked, key=f"v_coats_{unit_type}_{event_id}_{unit_no}")
        bags_eur  = c2.number_input(f"Taschen/Rucksäcke (€) – Stückpreis {bag_p:.2f} €", min_value=0.0, step=10.0, value=float(vals["bags_eur"]), disabled=locked, key=f"v_bags_{unit_type}_{event_id}_{unit_no}")
        total = coats_eur + bags_eur
        try:
            coats_qty = int(coats_eur // coat_p) if coat_p > 0 else 0
            bags_qty  = int(bags_eur  // bag_p)  if bag_p  > 0 else 0
        except Exception:
            coats_qty = bags_qty = 0
        st.info(f"Garderobe gesamt: **{total:,.2f} €** (≈ Jacken {coats_qty} | Taschen {bags_qty})", icon="🧥")
        payload = {"coats_eur": coats_eur, "bags_eur": bags_eur}

    colA, colB = st.columns([1,1])
    if colA.button("⬅️ Zur Übersicht", key=f"back_{event_id}_{unit_type}_{unit_no}", use_container_width=True):
        st.session_state.pop("cf_unit", None)
        st.rerun()

    if (not locked) and colB.button("💾 Speichern", key=f"save_{event_id}_{unit_type}_{unit_no}", type="primary", use_container_width=True):
        _save_unit_values(event_id, unit_type, unit_no, payload, username)
        st.success("Gespeichert.")

# -----------------------------
# Entry
# -----------------------------

def render_cashflow(current_user: str = "", current_role: str = "", scope: str = ""):
    _ensure_tables()

    st.title("💰 Abrechnung (Cashflow)")
    # Debug-Banner – hilft sofort zu erkennen, dass das NEUE Modul aktiv ist
    st.caption(f"🔎 Cashflow aktiv – User: {current_user or 'unknown'} | Role: {current_role or 'guest'} "
               f"| ev_id: {st.session_state.get('cf_event_id')} | sel: {st.session_state.get('cf_unit')}")

    # Event Header
    day_default = st.session_state.get("cf_day") or datetime.date.today()
    event_name_default = st.session_state.get("cf_name") or ""

    col1, col2, col3 = st.columns([1,2,1])
    day = col1.date_input("Event-Datum", value=day_default, key="cf_day")
    name = col2.text_input("Eventname", value=event_name_default, key="cf_name", placeholder="z. B. OZ / Halloween")

    rights = _user_rights(current_user or "", current_role or "")
    is_mgr = rights["is_admin_manager"]

    colX, colY = st.columns([1,1])
    open_pressed = colX.button("▶️ Event öffnen/fortsetzen", type="primary", use_container_width=True, disabled=(not name or not day))
    if open_pressed:
        st.session_state["cf_event_id"] = _get_or_create_event(day, name, current_user or "unknown")
        st.session_state.pop("cf_unit", None)
        st.rerun()

    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Bitte **Datum** und **Eventname** angeben und auf „Event öffnen/fortsetzen“ klicken.")
        return

    evt = _get_event(ev_id)
    if not evt:
        st.error("Event nicht gefunden. Bitte erneut öffnen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status, _, created_at, approved_by, approved_at = evt
    st.success(f"Event aktiv: **{ev_name}** am **{ev_day}** (Status: **{ev_status}**)")

    counts = _get_counts()
    if counts["bars"] + counts["registers"] + counts["cloakrooms"] == 0:
        st.warning("Keine Einheiten (Bars/Kassen/Garderobe) konfiguriert – bitte im Admin-Bereich unter „Betrieb“ Anzahl hinterlegen.")
        return

    unit_sel = st.session_state.get("cf_unit")
    locked = (ev_status == "approved") and (not is_mgr)

    if unit_sel:
        utype, uno = unit_sel
        _unit_editor(ev_id, utype, uno, current_user or "unknown", locked=locked)
    else:
        _unit_overview(ev_id, current_user or "unknown", rights, counts)

    st.markdown("---")
    if is_mgr:
        c1, c2, c3 = st.columns([1,1,2])
        if ev_status != "approved":
            if c1.button("✅ Tag freigeben (abschließen)", key=f"approve_{ev_id}", use_container_width=True):
                _set_event_status(ev_id, "approved", current_user or "unknown")
                st.success("Tag freigegeben. Einträge sind für Nicht-Manager gesperrt.")
                st.rerun()
        else:
            c2.caption("Event ist freigegeben.")
    else:
        if ev_status == "approved":
            st.info("Event ist freigegeben – Änderungen sind gesperrt. Bitte Betriebsleiter kontaktieren, wenn du noch etwas ändern musst.")
