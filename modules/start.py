# modules/start.py
import streamlit as st
import datetime
from typing import Dict, List, Optional
from core.db import conn
from core.config import APP_NAME, APP_VERSION

# ------------------------------------------------
# Helpers (minimal & robust)
# ------------------------------------------------

def _decode_units(units: str) -> Dict[str, List[int]]:
    out = {"bar": [], "cash": [], "cloak": []}
    if not units:
        return out
    for tok in [t.strip() for t in units.split(",") if t.strip()]:
        if ":" not in tok:
            continue
        t, v = tok.split(":", 1)
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
    """open = nicht freigegeben/geschlossen"""
    with conn() as cn:
        c = cn.cursor()
        return c.execute("""
            SELECT id, event_date, name, status
              FROM events
             WHERE status='open'
             ORDER BY event_date DESC, id DESC
        """).fetchall()

def _count_open_tasks_for_user(username: str, functions: str, units_str: str) -> int:
    """
    Für Admin/Betriebsleiter: Anzahl offener Events.
    Für Leiter (Bar/Kassa/Garderobe): Anzahl offener Events, bei denen er mindestens eine Unit zugewiesen hat.
    (Wir zählen nur Events – keine Unit-Details. Clean & schnell.)
    """
    open_events = _list_open_events()
    if not open_events:
        return 0

    if _is_admin_manager(functions):
        return len(open_events)

    assigned = _decode_units(units_str)
    if not any(assigned.values()):
        return 0

    # User hat mindestens eine Unit -> jedes offene Event ist für ihn relevant
    # (Wenn du es noch enger möchtest, könntest du hier prüfen, ob es Einträge für genau diese Units gibt.)
    return len(open_events)

# ------------------------------------------------
# UI
# ------------------------------------------------

def _hero_card(title: str, subtitle: str, badge: str = ""):
    st.markdown(
        f"""
        <style>
        .start-hero {{
            background: linear-gradient(180deg, rgba(34,34,48,0.9) 0%, rgba(18,18,28,0.9) 100%);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            padding: 20px 20px;
            box-shadow: 0 16px 38px rgba(0,0,0,0.35);
        }}
        .start-title {{
            font-size: 1.2rem; font-weight: 700; margin: 0;
        }}
        .start-sub {{
            opacity: .75; margin-top: 4px; font-size: .92rem;
        }}
        .start-badge {{
            display:inline-block; padding: 4px 10px; border-radius:999px;
            border:1px solid #FFFFFF22; font-size:.8rem; opacity:.85;
        }}
        .kpi {{
            font-size: 2rem; font-weight: 800; margin: 12px 0 2px 0;
        }}
        .kpi-sub {{
            opacity:.7; font-size:.85rem; margin-bottom: 12px;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )
    with st.container():
        st.markdown("<div class='start-hero'>", unsafe_allow_html=True)
        colA, colB = st.columns([3,1])
        with colA:
            st.markdown(f"<div class='start-title'>{title}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='start-sub'>{subtitle}</div>", unsafe_allow_html=True)
        with colB:
            if badge:
                st.markdown(f"<div style='text-align:right'><span class='start-badge'>{badge}</span></div>", unsafe_allow_html=True)

def _kpi_block(value: int, label: str):
    st.markdown(f"<div class='kpi'>{value}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='kpi-sub'>{label}</div>", unsafe_allow_html=True)

def _cta_buttons(is_mgr: bool):
    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("➡️ Zur Abrechnung", type="primary", use_container_width=True):
            st.session_state["nav_choice"] = "Abrechnung"
            st.rerun()
    with c2:
        if is_mgr:
            if st.button("🗂️ Event anlegen / bearbeiten", use_container_width=True):
                st.session_state["nav_choice"] = "Abrechnung"
                # Optional: Sprunganker für die Event-Verwaltung kannst du später via session flag bauen
                st.rerun()

def _activities():
    st.subheader("🕑 Letzte Aktivitäten")
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute("""
            SELECT ts, user, action, details
              FROM audit_log
             ORDER BY id DESC
             LIMIT 6
        """).fetchall()
    if not rows:
        st.caption("Noch keine Aktivitäten protokolliert.")
        return
    for ts, user, action, details in rows:
        st.markdown(f"- `{ts}` · **{user or '—'}** · *{action}* — {details}")

def _gastro_news():
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

# ------------------------------------------------
# Entry
# ------------------------------------------------

def render_start(username: str = "Gast"):
    # Kopfbereich / Hero
    user_row = _fetch_user(username)
    functions = (user_row[2] if user_row else "") or ""
    units_str = (user_row[3] if user_row else "") or ""
    is_mgr = _is_admin_manager(functions)

    _hero_card(
        title=f"Willkommen, {username or 'Gast'} 👋",
        subtitle="Hier siehst du auf einen Blick, ob Abrechnungen offen sind.",
        badge=f"{APP_NAME} v{APP_VERSION}"
    )

    # KPIs & CTA
    open_cnt = _count_open_tasks_for_user(username, functions, units_str)

    kpi_col, _ = st.columns([1,2])
    with kpi_col:
        _kpi_block(open_cnt, "offene Abrechnungstage")

    _cta_buttons(is_mgr)

    st.markdown("---")

    # Aktivitäten & News (zwei Spalten)
    left, right = st.columns([2,1])
    with left:
        _activities()
    with right:
        _gastro_news()
