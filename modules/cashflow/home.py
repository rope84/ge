import streamlit as st
import datetime
from typing import Dict, List, Optional, Tuple
from core.db import conn

META_KEYS = {
    "bars": ["bars_count", "business_bars", "num_bars"],
    "registers": ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

# ---- Meta & Counts ----
def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def _counts() -> Dict[str, int]:
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

# ---- Schema helpers ----
def _ensure_schema():
    with conn() as cn:
        c = cn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_by TEXT,
                created_at TEXT,
                approved_by TEXT,
                approved_at TEXT
            )
        """)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date, name)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_unit_status (
                event_id   INTEGER NOT NULL,
                unit_type  TEXT    NOT NULL,
                unit_no    INTEGER NOT NULL,
                done_by    TEXT,
                done_at    TEXT,
                PRIMARY KEY (event_id, unit_type, unit_no)
            )
        """)
        cn.commit()

def _get_or_create_event(day: datetime.date, name: str, user: str) -> int:
    _ensure_schema()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT id FROM events WHERE event_date=? AND name=?", (day.isoformat(), name.strip())).fetchone()
        if row:
            return row[0]
        c.execute(
            "INSERT INTO events(event_date, name, status, created_by, created_at) VALUES(?,?,?,?,datetime('now'))",
            (day.isoformat(), name.strip(), "open", user),
        )
        cn.commit()
        return c.lastrowid

def _event_info(event_id: int) -> Optional[Tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute("SELECT id, event_date, name, status FROM events WHERE id=?", (event_id,)).fetchone()

# ---- Per-Unit Totals & Status ----
def _unit_total(event_id: int, unit_type: str, unit_no: int) -> float:
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT field, value FROM cashflow_item
            WHERE event_id=? AND unit_type=? AND unit_no=?
        """, (event_id, unit_type, unit_no)).fetchall()
    vals = {k: 0.0 for k in ["cash","pos1","pos2","pos3","voucher","tables","card","coats_eur","bags_eur"]}
    for f, v in rows:
        try:
            vals[f] = float(v)
        except Exception:
            pass
    if unit_type == "bar":
        return vals["cash"] + vals["pos1"] + vals["pos2"] + vals["pos3"] + vals["voucher"]
    if unit_type == "cash":
        return vals["cash"] + vals["card"]
    return vals["coats_eur"] + vals["bags_eur"]

def _unit_done(event_id: int, unit_type: str, unit_no: int) -> bool:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("""
            SELECT 1 FROM cashflow_unit_status
            WHERE event_id=? AND unit_type=? AND unit_no=?
        """, (event_id, unit_type, unit_no)).fetchone()
        return r is not None

# ---- History (nur eigene für Barleiter) ----
def _my_history(username: str, limit: int = 10) -> List[Tuple]:
    # Liefert: (event_date, name, unit_type, unit_no, total)
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT e.event_date, e.name, ci.unit_type, ci.unit_no,
                   SUM(CASE
                         WHEN ci.unit_type='bar'  AND ci.field IN ('cash','pos1','pos2','pos3','voucher') THEN ci.value
                         WHEN ci.unit_type='cash' AND ci.field IN ('cash','card') THEN ci.value
                         WHEN ci.unit_type='cloak' AND ci.field IN ('coats_eur','bags_eur') THEN ci.value
                         ELSE 0
                       END) AS total
            FROM cashflow_item ci
            JOIN events e ON e.id = ci.event_id
            WHERE e.status='approved' AND ci.updated_by=?
            GROUP BY e.event_date, e.name, ci.unit_type, ci.unit_no
            ORDER BY e.event_date DESC, e.name DESC
            LIMIT ?
        """, (username, limit)).fetchall()
    return rows or []

# ---- UI helpers ----
def _tile(label: str, subtitle: str, key: str, disabled: bool=False) -> bool:
    with st.container(border=True):
        st.markdown(f"**{label}**  \n<span style='opacity:.7;font-size:12px'>{subtitle}</span>", unsafe_allow_html=True)
        return st.button("Bearbeiten" if not disabled else "Ansehen", key=key, use_container_width=True, disabled=disabled)

# ---- Render ----
def render_cashflow_home():
    _ensure_schema()
    st.subheader("")

    user = st.session_state.get("username") or "unknown"
    role = (st.session_state.get("role") or "").lower()
    funcs = (st.session_state.get("functions") or "").lower()
    is_mgr = (role == "admin") or ("admin" in funcs) or ("betriebsleiter" in funcs)
    is_bar = ("barleiter" in funcs)
    is_kas = ("kassa" in funcs)
    is_clo = ("garderobe" in funcs)

    # 1) Event-Auswahl / -Anlage
    col1, col2 = st.columns([1,2])
    day = col1.date_input("Event-Datum", value=st.session_state.get("cf_day") or datetime.date.today(), key="cf_day")
    name = col2.text_input("Eventname", value=st.session_state.get("cf_name") or "", key="cf_name", placeholder="z. B. OZ / Halloween")

    # Dropdown aller Events des ausgewählten Tages
    with conn() as cn:
        c = cn.cursor()
        options = c.execute(
            "SELECT id, name, status FROM events WHERE event_date=? ORDER BY created_at DESC",
            (day.isoformat(),)
        ).fetchall()

    nice = [f"{e[0]} – {e[1]} ({e[2]})" for e in options]
    ev_select = st.selectbox("Event wählen", options=list(zip([o[0] for o in options], nice)), format_func=lambda x: x[1] if isinstance(x, tuple) else x, key="cf_event_select") if options else None

    cols = st.columns(2)
    if is_mgr:
        if cols[0].button("▶️ Event öffnen/fortsetzen", type="primary", use_container_width=True, disabled=(not name or not day)):
            ev_id = _get_or_create_event(day, name, user)
            st.session_state["cf_event_id"] = ev_id
            st.session_state.pop("cf_unit", None)
            st.success("Event aktiv.")
            st.rerun()
        if ev_select:
            ev_id = ev_select[0] if isinstance(ev_select, tuple) else ev_select
            if cols[1].button("Öffnen (Auswahl)", use_container_width=True):
                st.session_state["cf_event_id"] = int(ev_id)
                st.session_state.pop("cf_unit", None)
                st.rerun()
    else:
        st.caption("Event wird vom Betriebsleiter freigegeben. Danach kannst du deine Einheit bearbeiten.")

    # Falls aktives Event vorhanden
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        # Barleiter sehen hier schon den Rückblick
        if not is_mgr:
            st.markdown("### Rückblick (deine vergangenen Abrechnungen)")
            rows = _my_history(user, limit=20)
            if not rows:
                st.info("Keine vergangenen Abrechnungen gefunden.")
            else:
                for d, n, ut, uno, tot in rows:
                    st.markdown(f"- **{d} – {n}** · {ut.upper()} #{uno} · {tot:,.2f} €")
        else:
            st.info("Kein Event/Tag vorhanden.")
        return

    evt = _event_info(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut öffnen.")
        st.session_state.pop("cf_event_id", None)
        return

    _, ev_day, ev_name, ev_status = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    # Wenn Event freigegeben ist, Barleiter hat keinen Zugriff → Event aus Session, Rückblick zeigen
    if (ev_status == "approved") and (not is_mgr):
        st.info("Dieses Event ist abgeschlossen. Du kannst deine vergangenen Abrechnungen unten einsehen.")
        st.session_state.pop("cf_event_id", None)
        st.session_state.pop("cf_unit", None)
        st.rerun()
        return

    # 2) Kacheln
    cnt = _counts()
    if cnt["bars"] + cnt["registers"] + cnt["cloakrooms"] == 0:
        st.warning("Keine Einheiten konfiguriert – bitte unter Admin → Betrieb definieren.")
        return

    def _render_unit_group(title: str, unit_type: str, count: int, allowed: bool):
        if not count or not allowed:
            return
        st.caption(title)
        cols = st.columns(min(4, max(1, count)))
        ci = 0
        for i in range(1, count+1):
            total = _unit_total(ev_id, unit_type, i)
            done  = _unit_done(ev_id, unit_type, i)
            label = f"{title[:-1]} {i} – {total:,.2f} €" if total > 0 else f"{title[:-1]} {i}"
            status = "✔ erledigt" if done else "⏳ offen"
            subtitle = f"{status}"
            disabled = (ev_status == "approved") and is_mgr is False
            with cols[ci]:
                if _tile(label, subtitle, key=f"cf_open_{unit_type}_{ev_id}_{i}", disabled=disabled and not is_mgr):
                    st.session_state["cf_unit"] = (unit_type, i)
                    # Wenn approved und Manager → nur ansehen im Wizard (locked dort)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)

    _render_unit_group("Bars",      "bar",   cnt["bars"],      allowed=(is_mgr or is_bar))
    _render_unit_group("Kassen",    "cash",  cnt["registers"], allowed=(is_mgr or is_kas))
    _render_unit_group("Garderoben","cloak", cnt["cloakrooms"],allowed=(is_mgr or is_clo))

    # 3) Rückblick (nur Barleiter)
    if not is_mgr:
        st.markdown("---")
        st.markdown("### Rückblick (deine vergangenen Abrechnungen)")
        rows = _my_history(user, limit=20)
        if not rows:
            st.info("Keine vergangenen Abrechnungen gefunden.")
        else:
            for d, n, ut, uno, tot in rows:
                st.markdown(f"- **{d} – {n}** · {ut.upper()} #{uno} · {tot:,.2f} €")
