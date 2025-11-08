# modules/cashflow/home.py
import streamlit as st
import datetime
from typing import Dict, List, Optional, Tuple
from core.db import conn

META_KEYS = {
    "bars": ["bars_count", "business_bars", "num_bars"],
    "registers": ["registers_count", "business_registers", "num_registers", "kassen_count"],
    "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
}

# ---------------- DB/Schema & Meta ----------------

def _ensure_schema():
    with conn() as cn:
        c = cn.cursor()
        # Events
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date   TEXT NOT NULL,
                name         TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'open',   -- open | approved | closed
                created_by   TEXT,
                created_at   TEXT,
                approved_by  TEXT,
                approved_at  TEXT,
                bars_open        INTEGER,
                registers_open   INTEGER,
                cloakrooms_open  INTEGER
            )
        """)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_events_day_name ON events(event_date, name)")
        # Migrations – fehlende Spalten nachziehen
        c.execute("PRAGMA table_info(events)")
        cols = {row[1] for row in c.fetchall()}
        if "bars_open" not in cols:
            c.execute("ALTER TABLE events ADD COLUMN bars_open INTEGER")
        if "registers_open" not in cols:
            c.execute("ALTER TABLE events ADD COLUMN registers_open INTEGER")
        if "cloakrooms_open" not in cols:
            c.execute("ALTER TABLE events ADD COLUMN cloakrooms_open INTEGER")
        # cashflow_item für Status/Editor
        c.execute("""
            CREATE TABLE IF NOT EXISTS cashflow_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id  INTEGER NOT NULL,
                unit_type TEXT NOT NULL,   -- bar|cash|cloak
                unit_no   INTEGER NOT NULL,
                field     TEXT NOT NULL,   -- cash,pos1,pos2,pos3,voucher,tables|card|coats_eur,bags_eur
                value     REAL  NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TEXT,
                UNIQUE(event_id, unit_type, unit_no, field)
            )
        """)
        cn.commit()

def _get_meta(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def _global_counts() -> Dict[str, int]:
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

# ---------------- Events CRUD ----------------

def _get_or_create_event(day: datetime.date, name: str, user: str) -> int:
    _ensure_schema()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT id FROM events WHERE event_date=? AND name=?",
            (day.isoformat(), name.strip()),
        ).fetchone()
        if row:
            return row[0]
        c.execute(
            "INSERT INTO events(event_date, name, status, created_by, created_at) "
            "VALUES(?,?,?,?, datetime('now'))",
            (day.isoformat(), name.strip(), "open", user),
        )
        cn.commit()
        return c.lastrowid

def _list_events_for_day(day: datetime.date):
    _ensure_schema()
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            "SELECT id, name, status, bars_open, registers_open, cloakrooms_open "
            "FROM events WHERE event_date=? ORDER BY created_at DESC, id DESC",
            (day.isoformat(),),
        ).fetchall()
    return rows

def _load_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, event_date, name, status, bars_open, registers_open, cloakrooms_open "
            "FROM events WHERE id=?",
            (event_id,),
        ).fetchone()

def _delete_event(event_id: int):
    with conn() as cn:
        c = cn.cursor()
        c.execute("DELETE FROM cashflow_item WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM events WHERE id=?", (event_id,))
        cn.commit()

def _save_event_unit_counts(event_id: int, bars: int, regs: int, cloaks: int):
    with conn() as cn:
        c = cn.cursor()
        c.execute(
            "UPDATE events SET bars_open=?, registers_open=?, cloakrooms_open=? WHERE id=?",
            (bars, regs, cloaks, event_id),
        )
        cn.commit()

# ---------------- Unit Status helpers ----------------

def _unit_done(event_id: int, unit_type: str, unit_no: int) -> bool:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute(
            "SELECT 1 FROM cashflow_item WHERE event_id=? AND unit_type=? AND unit_no=? LIMIT 1",
            (event_id, unit_type, unit_no),
        ).fetchone()
    return bool(r)

def _event_effective_counts(event_row, global_counts: Dict[str, int]) -> Dict[str, int]:
    """Nimmt per-Event Overrides, sonst globale Counts."""
    _, _, _, _, bars_open, regs_open, cloaks_open = event_row
    return {
        "bars": bars_open if isinstance(bars_open, int) and bars_open is not None else global_counts["bars"],
        "registers": regs_open if isinstance(regs_open, int) and regs_open is not None else global_counts["registers"],
        "cloakrooms": cloaks_open if isinstance(cloaks_open, int) and cloaks_open is not None else global_counts["cloakrooms"],
    }

# ---------------- UI ----------------

def _tile(label: str, subtitle: str, status_icon: str, key: str) -> bool:
    with st.container(border=True):
        st.markdown(
            f"**{label}** {status_icon}  \n"
            f"<span style='opacity:.7;font-size:12px'>{subtitle}</span>",
            unsafe_allow_html=True
        )
        return st.button("Bearbeiten", key=key, use_container_width=True)

def render_cashflow_home(is_mgr: bool, is_bar: bool, is_kas: bool, is_clo: bool):
    # KEINE zusätzliche Überschrift mehr
    _ensure_schema()

    # Event-Header
    default_day = st.session_state.get("cf_event_day") or datetime.date.today()
    default_name = st.session_state.get("cf_event_name") or ""

    col1, col2 = st.columns([1, 2])
    day = col1.date_input("Event-Datum", value=default_day, key="cf_day")
    name = col2.text_input("Eventname", value=default_name, key="cf_name", placeholder="z. B. OZ / Halloween")

    # Manager: Event öffnen/neu anlegen
    if is_mgr:
        topA, topB, topC = st.columns([1, 1, 2])
        if topA.button("▶️ Event öffnen/fortsetzen", type="primary", use_container_width=True, disabled=(not name or not day)):
            ev_id = _get_or_create_event(day, name, st.session_state.get("username") or "unknown")
            st.session_state["cf_event_id"]   = ev_id
            st.session_state["cf_event_day"]  = day
            st.session_state["cf_event_name"] = name
            st.session_state["cf_active_tab"] = "home"
            st.rerun()
    else:
        st.caption("Event wird vom Betriebsleiter gestartet. Danach kannst du deine Einheit bearbeiten.")

    # Manager: Event-Auswahl (alle Events für gewählten Tag)
    if is_mgr:
        events_today = _list_events_for_day(day)
        if events_today:
            ev_labels = [f"{nm}  •  ({stt})" for (_id, nm, stt, *_rest) in events_today]
            current_ev = st.session_state.get("cf_event_id")
            try:
                pre_idx = next((i for i, (eid, *_r) in enumerate(events_today) if eid == current_ev), 0)
            except Exception:
                pre_idx = 0
            sel_idx = st.selectbox("Event an diesem Tag auswählen", range(len(events_today)),
                                   format_func=lambda i: ev_labels[i], index=pre_idx)
            sel_id, sel_name, sel_status, b_open, r_open, c_open = events_today[sel_idx]

            colA, colB, colC = st.columns([1, 1, 2])
            if colA.button("Aktivieren", use_container_width=True, key="btn_pick_event"):
                st.session_state["cf_event_id"]   = sel_id
                st.session_state["cf_event_day"]  = day
                st.session_state["cf_event_name"] = sel_name
                st.session_state["cf_active_tab"] = "home"
                st.rerun()

            # Danger-Zone: Event löschen
            with colB:
                st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
                confirm = st.checkbox("Ich bestätige das Löschen", key="cf_del_confirm")
                del_disabled = not confirm
                if st.button("🗑️ Event löschen", use_container_width=True, disabled=del_disabled, key="btn_delete_event"):
                    _delete_event(sel_id)
                    if st.session_state.get("cf_event_id") == sel_id:
                        st.session_state.pop("cf_event_id", None)
                    st.success("Event gelöscht.")
                    st.rerun()
        else:
            st.info("Für dieses Datum gibt es noch keine Events. Du kannst oben durch „Event öffnen/fortsetzen“ ein neues anlegen.")

    # Aktives Event
    ev_id = st.session_state.get("cf_event_id")
    if not ev_id:
        st.info("Kein Event/Tag vorhanden.")
        return

    evt = _load_event(ev_id)
    if not evt:
        st.warning("Event nicht gefunden – bitte erneut öffnen/aktivieren.")
        st.session_state.pop("cf_event_id", None)
        return

    _id, ev_day, ev_name, ev_status, ev_bars_open, ev_regs_open, ev_clo_open = evt
    st.success(f"Aktives Event: **{ev_name}** am **{ev_day}** (Status: {ev_status})")

    # Per-Event Einheiten-Konfiguration (Overrides)
    g_counts = _global_counts()
    eff = _event_effective_counts(evt, g_counts)

    if is_mgr:
        st.markdown("#### Einheiten für diesen Tag (Optional)")
        e1, e2, e3, e4 = st.columns([1,1,1,1])
        bars_open = e1.number_input("Bars aktiv", min_value=0, step=1, value=int(eff["bars"]), key="cfg_bars_open")
        regs_open = e2.number_input("Kassen aktiv", min_value=0, step=1, value=int(eff["registers"]), key="cfg_regs_open")
        clo_open  = e3.number_input("Garderoben aktiv", min_value=0, step=1, value=int(eff["cloakrooms"]), key="cfg_clo_open")
        if e4.button("💾 Speichern", use_container_width=True, key="btn_save_event_counts"):
            _save_event_unit_counts(ev_id, bars_open, regs_open, clo_open)
            st.success("Einheiten für diesen Tag gespeichert.")
            st.rerun()
        eff = {"bars": bars_open, "registers": regs_open, "cloakrooms": clo_open}

    st.markdown("---")

    # Einheiten-Kacheln + Status
    # Sichtbarkeit simpel nach Rolle; (feingranular per User-Unit-Zuweisung kann in utils ergänzt werden)
    # Bars
    if is_mgr or is_bar:
        st.caption("Bars")
        cols = st.columns(min(4, max(1, eff["bars"])))
        ci = 0
        for i in range(1, eff["bars"] + 1):
            done = _unit_done(ev_id, "bar", i)
            icon = "✅" if done else "⏳"
            with cols[ci]:
                if _tile(f"Bar {i}", "Umsatz & Voucher erfassen", icon, key=f"cf_open_bar_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("bar", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)

    # Kassen
    if is_mgr or is_kas:
        st.caption("Kassen")
        cols = st.columns(min(4, max(1, eff["registers"])))
        ci = 0
        for i in range(1, eff["registers"] + 1):
            done = _unit_done(ev_id, "cash", i)
            icon = "✅" if done else "⏳"
            with cols[ci]:
                if _tile(f"Kassa {i}", "Bar/Unbar (Karten) erfassen", icon, key=f"cf_open_cash_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cash", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)

    # Garderoben
    if is_mgr or is_clo:
        st.caption("Garderoben")
        cols = st.columns(min(4, max(1, eff["cloakrooms"])))
        ci = 0
        for i in range(1, eff["cloakrooms"] + 1):
            done = _unit_done(ev_id, "cloak", i)
            icon = "✅" if done else "⏳"
            with cols[ci]:
                if _tile(f"Garderobe {i}", "Jacken/Taschen erfassen", icon, key=f"cf_open_cloak_{ev_id}_{i}"):
                    st.session_state["cf_unit"] = ("cloak", i)
                    st.session_state["cf_active_tab"] = "wizard"
                    st.rerun()
            ci = (ci + 1) % len(cols)
