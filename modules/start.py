# start.py
import streamlit as st
import datetime
from typing import Dict, List, Optional, Tuple
import random
from core.db import conn
from core.ui_theme import page_header
from core.config import APP_NAME, APP_VERSION

# -----------------------------
# Helpers
# -----------------------------

def _decode_units(units: str) -> Dict[str, List[int]]:
    """
    Erwartetes Format: "bar:1,bar:2,cash:1,cloak:1"
    """
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

def _fetch_user(username: str) -> Optional[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute(
            "SELECT id, username, functions, units FROM users WHERE username=?",
            (username,),
        ).fetchone()

def _is_admin_manager(functions: str) -> bool:
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    return ("admin" in funcs) or ("betriebsleiter" in funcs)

def _list_open_events() -> List[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute("""
            SELECT id, event_date, name, status
              FROM events
             WHERE status='open'
             ORDER BY event_date DESC, id DESC
        """).fetchall()

def _sum_for_unit(event_id: int, unit_type: str, unit_no: int) -> float:
    """
    Summiert die relevanten Felder je Einheit.
    bar  : cash + pos1 + pos2 + pos3 + voucher
    cash : cash + card
    cloak: coats_eur + bags_eur
    """
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            """SELECT field, value FROM cashflow_item
               WHERE event_id=? AND unit_type=? AND unit_no=?""",
            (event_id, unit_type, unit_no)
        ).fetchall()
    values = {k: 0.0 for k in ["cash","pos1","pos2","pos3","voucher","tables","card","coats_eur","bags_eur"]}
    for f,v in rows:
        try:
            values[f] = float(v)
        except Exception:
            pass
    if unit_type == "bar":
        return values["cash"]+values["pos1"]+values["pos2"]+values["pos3"]+values["voucher"]
    if unit_type == "cash":
        return values["cash"]+values["card"]
    return values["coats_eur"]+values["bags_eur"]

def _meta_get(key: str) -> Optional[str]:
    with conn() as cn:
        c = cn.cursor()
        r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

def _counts() -> Dict[str, int]:
    MAP = {
        "bars": ["bars_count", "business_bars", "num_bars"],
        "registers": ["registers_count", "business_registers", "num_registers", "kassen_count"],
        "cloakrooms": ["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"],
    }
    def _first_int(keys: List[str], dflt: int = 0) -> int:
        for k in keys:
            v = _meta_get(k)
            if v is not None and str(v).strip() != "":
                try:
                    return max(0, int(float(str(v).strip())))
                except Exception:
                    continue
        return dflt
    return {
        "bars": _first_int(MAP["bars"], 0),
        "registers": _first_int(MAP["registers"], 0),
        "cloakrooms": _first_int(MAP["cloakrooms"], 0),
    }

def _recent_audit(limit: int = 8) -> List[tuple]:
    with conn() as cn:
        c = cn.cursor()
        return c.execute("""
            SELECT ts, user, action, details
              FROM audit_log
             ORDER BY id DESC
             LIMIT ?
        """, (limit,)).fetchall()

# -----------------------------
# UI bits
# -----------------------------

def _task_tile(label: str, sub: str, key: str, on_click=None):
    with st.container(border=True):
        st.markdown(f"**{label}**  \n<span style='opacity:.75;font-size:12px'>{sub}</span>", unsafe_allow_html=True)
        if st.button("Bearbeiten", key=key, use_container_width=True):
            if callable(on_click):
                on_click()

def _goto_abrechnung(event_id: int, unit_type: Optional[str] = None, unit_no: Optional[int] = None):
    s = st.session_state
    s["cf_event_id"] = event_id
    if unit_type and unit_no:
        s["cf_unit"] = (unit_type, unit_no)
    s["nav_choice"] = "Abrechnung"
    st.rerun()

# -----------------------------
# Start / Dashboard
# -----------------------------

def render_start(username: str = "Gast"):
    st.title("👋 Willkommen")
    st.caption("Dein Cockpit für offene Aufgaben und Neuigkeiten.")

    # User laden
    row = _fetch_user(username)
    functions = (row[2] if row else "") or ""
    units_str = (row[3] if row else "") or ""
    assigned = _decode_units(units_str)
    is_mgr = _is_admin_manager(functions)

    # Layout
    left, right = st.columns([2,1])

    # ---- Linke Spalte: Aufgaben & Aktionen ----
    with left:
        st.subheader("🧾 Offene Aufgaben")

        open_events = _list_open_events()
        counts = _counts()

        if not open_events:
            st.info("Aktuell sind keine offenen Events vorhanden.")
        else:
            # Betriebsleiter/Admin: Übersicht über alle offenen Events + Kacheln je Einheit (nur Status)
            if is_mgr:
                for (ev_id, ev_day, ev_name, ev_status) in open_events:
                    st.markdown(f"**{ev_name}** — {ev_day}  · Status: *{ev_status}*")
                    # Kacheln je Einheit (nur Status + Bearbeiten → springt in die Abrechnung)
                    # Bars
                    if counts["bars"]:
                        st.caption("Bars")
                        cols = st.columns(min(4, max(1, counts["bars"])))
                        ci = 0
                        for i in range(1, counts["bars"]+1):
                            total = _sum_for_unit(ev_id, "bar", i)
                            label = f"Bar {i}"
                            sub = "noch nichts erfasst" if total <= 0 else f"Umsatz: {total:,.2f} €"
                            with cols[ci]:
                                _task_tile(
                                    label, sub,
                                    key=f"start_mgr_bar_{ev_id}_{i}",
                                    on_click=lambda eid=ev_id,u="bar",no=i: _goto_abrechnung(eid,u,no)
                                )
                            ci = (ci + 1) % len(cols)

                    # Kassen
                    if counts["registers"]:
                        st.caption("Kassen")
                        cols = st.columns(min(4, max(1, counts["registers"])))
                        ci = 0
                        for i in range(1, counts["registers"]+1):
                            total = _sum_for_unit(ev_id, "cash", i)
                            label = f"Kassa {i}"
                            sub = "noch nichts erfasst" if total <= 0 else f"Gesamt: {total:,.2f} €"
                            with cols[ci]:
                                _task_tile(
                                    label, sub,
                                    key=f"start_mgr_cash_{ev_id}_{i}",
                                    on_click=lambda eid=ev_id,u="cash",no=i: _goto_abrechnung(eid,u,no)
                                )
                            ci = (ci + 1) % len(cols)

                    # Garderoben
                    if counts["cloakrooms"]:
                        st.caption("Garderoben")
                        cols = st.columns(min(4, max(1, counts["cloakrooms"])))
                        ci = 0
                        for i in range(1, counts["cloakrooms"]+1):
                            total = _sum_for_unit(ev_id, "cloak", i)
                            label = f"Garderobe {i}"
                            sub = "noch nichts erfasst" if total <= 0 else f"Gesamt: {total:,.2f} €"
                            with cols[ci]:
                                _task_tile(
                                    label, sub,
                                    key=f"start_mgr_cloak_{ev_id}_{i}",
                                    on_click=lambda eid=ev_id,u="cloak",no=i: _goto_abrechnung(eid,u,no)
                                )
                            ci = (ci + 1) % len(cols)

                    st.divider()

            # Leiter (Bar/Kassa/Garderobe): nur eigene Units je offenem Event
            else:
                for (ev_id, ev_day, ev_name, ev_status) in open_events:
                    st.markdown(f"**{ev_name}** — {ev_day}  · Status: *{ev_status}*")
                    # Bars (nur zugewiesene)
                    if assigned["bar"]:
                        st.caption("Deine Bars")
                        cols = st.columns(min(4, max(1, len(assigned["bar"]))))
                        ci = 0
                        for i in assigned["bar"]:
                            if i <= 0: 
                                continue
                            total = _sum_for_unit(ev_id, "bar", i)
                            sub = "noch nichts erfasst" if total <= 0 else f"Umsatz: {total:,.2f} €"
                            with cols[ci]:
                                _task_tile(
                                    f"Bar {i}", sub,
                                    key=f"start_bar_{ev_id}_{i}",
                                    on_click=lambda eid=ev_id,u="bar",no=i: _goto_abrechnung(eid,u,no)
                                )
                            ci = (ci + 1) % len(cols)

                    # Kassen
                    if assigned["cash"]:
                        st.caption("Deine Kassen")
                        cols = st.columns(min(4, max(1, len(assigned["cash"]))))
                        ci = 0
                        for i in assigned["cash"]:
                            if i <= 0:
                                continue
                            total = _sum_for_unit(ev_id, "cash", i)
                            sub = "noch nichts erfasst" if total <= 0 else f"Gesamt: {total:,.2f} €"
                            with cols[ci]:
                                _task_tile(
                                    f"Kassa {i}", sub,
                                    key=f"start_cash_{ev_id}_{i}",
                                    on_click=lambda eid=ev_id,u="cash",no=i: _goto_abrechnung(eid,u,no)
                                )
                            ci = (ci + 1) % len(cols)

                    # Garderoben
                    if assigned["cloak"]:
                        st.caption("Deine Garderoben")
                        cols = st.columns(min(4, max(1, len(assigned["cloak"]))))
                        ci = 0
                        for i in assigned["cloak"]:
                            if i <= 0:
                                continue
                            total = _sum_for_unit(ev_id, "cloak", i)
                            sub = "noch nichts erfasst" if total <= 0 else f"Gesamt: {total:,.2f} €"
                            with cols[ci]:
                                _task_tile(
                                    f"Garderobe {i}", sub,
                                    key=f"start_cloak_{ev_id}_{i}",
                                    on_click=lambda eid=ev_id,u="cloak",no=i: _goto_abrechnung(eid,u,no)
                                )
                            ci = (ci + 1) % len(cols)

                    st.divider()

        # Quick Actions
        st.subheader("⚡ Schnellzugriff")
        q1, q2, q3 = st.columns(3)
        with q1:
            if st.button("Abrechnung öffnen", use_container_width=True):
                st.session_state["nav_choice"] = "Abrechnung"
                st.rerun()
        with q2:
            if st.button("Inventur", use_container_width=True):
                st.session_state["nav_choice"] = "Inventur"
                st.rerun()
        with q3:
            if (_is_admin_manager(functions)) and st.button("Admin-Cockpit", use_container_width=True):
                st.session_state["nav_choice"] = "Admin-Cockpit"
                st.rerun()

        # Letzte Aktivitäten
        st.subheader("🕑 Letzte Aktivitäten")
        logs = _recent_audit()
        if not logs:
            st.caption("Noch keine Aktivitäten protokolliert.")
        else:
            for ts, user, action, details in logs:
                st.markdown(f"- `{ts}` · **{user or '—'}** · *{action}* — {details}")

    # ---- Rechte Spalte: News ----
    with right:
        st.subheader("📰 Gastro-News")
        st.caption("(optional, per RSS – wird nur angezeigt, wenn abrufbar)")
        try:
            import feedparser
            FEEDS = [
                "https://www.falstaff.at/rss.xml",
                "https://www.rollingpin.at/feed",
                "https://www.gastronews.wien/feed/",
            ]
            for url in FEEDS:
                d = feedparser.parse(url)
                if d.bozo:
                    continue
                if d.feed.get("title"):
                    st.markdown(f"**{d.feed.title}**")
                for entry in (d.entries or [])[:3]:
                    title = entry.get("title", "ohne Titel")
                    link  = entry.get("link", None)
                    if link:
                        st.markdown(f"- [{title}]({link})")
                    else:
                        st.markdown(f"- {title}")
                st.markdown("---")
        except Exception:
            st.caption("RSS nicht verfügbar.")
