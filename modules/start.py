# modules/start.py
import streamlit as st
from typing import Dict, List, Optional, Tuple
from core.db import conn
from core.config import APP_NAME, APP_VERSION

# ------------------------------------------------
# DB-Helpers (robust & schema-aware)
# ------------------------------------------------

def _table_exists(c, name: str) -> bool:
    return c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None

def _has_column(c, table: str, col: str) -> bool:
    try:
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        return col in cols
    except Exception:
        return False

# ------------------------------------------------
# Generic helpers
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

def _fetch_user_row(username: str) -> Optional[Tuple[int, str, str, str]]:
    """Gibt (id, username, functions, units_str) zurück — units_str='' wenn Spalte fehlt oder leer."""
    if not username:
        return None
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, "users"):
            return None
        has_units = _has_column(c, "users", "units")
        if has_units:
            row = c.execute(
                "SELECT id, username, functions, COALESCE(units,'') FROM users WHERE username=?",
                (username,),
            ).fetchone()
            return row
        else:
            row = c.execute(
                "SELECT id, username, functions FROM users WHERE username=?",
                (username,),
            ).fetchone()
            if not row:
                return None
            return (row[0], row[1], row[2], "")

def _is_admin_manager(functions: str) -> bool:
    funcs = [f.strip().lower() for f in (functions or "").split(",") if f.strip()]
    return ("admin" in funcs) or ("betriebsleiter" in funcs)

# ------------------------------------------------
# Business helpers
# ------------------------------------------------

def _get_int_meta(keys: List[str], default: int = 0) -> int:
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, "meta"):
            return default
        for k in keys:
            r = c.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
            if r and str(r[0]).strip() != "":
                try:
                    return max(0, int(float(str(r[0]).strip())))
                except Exception:
                    continue
    return default

def _counts_from_meta() -> Dict[str, int]:
    return {
        "bars": _get_int_meta(["bars_count", "business_bars", "num_bars"], 0),
        "registers": _get_int_meta(["registers_count", "business_registers", "num_registers", "kassen_count"], 0),
        "cloakrooms": _get_int_meta(["cloakrooms_count", "business_cloakrooms", "num_cloakrooms", "garderoben_count"], 0),
    }

def _event_stats() -> Tuple[int, int]:
    """
    Liefert (open_count, closed_count).
    closed = Events mit status != 'open' (robust, falls andere Stati existieren).
    """
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, "events"):
            return (0, 0)
        open_cnt = c.execute("SELECT COUNT(*) FROM events WHERE status='open'").fetchone()[0]
        total = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        # closed/approved/etc. = total - open (robust, falls andere Stati genutzt werden)
        closed_cnt = max(0, (total or 0) - (open_cnt or 0))
        return (open_cnt or 0, closed_cnt or 0)

def _latest_closed_event_id() -> Optional[int]:
    """Nimmt zuerst einen geschlossenen/abgeschlossenen Event, sonst den jüngsten beliebigen."""
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, "events"):
            return None
        # bevorzugt: closed/approved (status != 'open'); nach Datum, dann ID
        row = c.execute("""
            SELECT id FROM events
             WHERE COALESCE(status,'open') <> 'open'
             ORDER BY COALESCE(event_date,'9999-12-31') DESC, id DESC
             LIMIT 1
        """).fetchone()
        if row:
            return row[0]
        # Fallback: jüngster Event
        row = c.execute("""
            SELECT id FROM events
             ORDER BY COALESCE(event_date,'9999-12-31') DESC, id DESC
             LIMIT 1
        """).fetchone()
        return row[0] if row else None

def _sum_for_unit(event_id: int, unit_type: str, unit_no: int) -> float:
    """
    Summiert Felder je Einheit:
    - bar  : cash + pos1 + pos2 + pos3 + voucher
    - cash : cash + card
    - cloak: coats_eur + bags_eur
    """
    if event_id is None:
        return 0.0
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, "cashflow_item"):
            return 0.0
        rows = c.execute(
            """SELECT field, value FROM cashflow_item
               WHERE event_id=? AND unit_type=? AND unit_no=?""",
            (event_id, unit_type, unit_no),
        ).fetchall()
    values = {k: 0.0 for k in ["cash","pos1","pos2","pos3","voucher","card","coats_eur","bags_eur"]}
    for f, v in rows:
        try:
            values[f] = float(v)
        except Exception:
            pass
    if unit_type == "bar":
        return values["cash"] + values["pos1"] + values["pos2"] + values["pos3"] + values["voucher"]
    if unit_type == "cash":
        return values["cash"] + values["card"]
    return values["coats_eur"] + values["bags_eur"]

# ------------------------------------------------
# UI building blocks (Admin-Cockpit Stil)
# ------------------------------------------------

def _card_html(title: str, color: str, lines: List[str]) -> str:
    body = "<br/>".join([f"<span style='opacity:.85;font-size:12px'>{ln}</span>" for ln in lines])
    return f"""
    <div style="
        display:flex; gap:12px; align-items:flex-start;
        padding:12px 14px; border-radius:14px;
        background:rgba(255,255,255,0.03);
        box-shadow:0 6px 16px rgba(0,0,0,0.15);
        position:relative; overflow:hidden;">
      <div style="
        position:absolute; left:0; top:0; bottom:0; width:6px;
        background:linear-gradient(180deg,{color},{color}55);
        border-top-left-radius:14px; border-bottom-left-radius:14px;"></div>
      <div style="width:10px; height:10px; border-radius:50%; background:{color}; margin-top:4px;"></div>
      <div style="font-size:13px;">
        <b>{title}</b><br/>{body}
      </div>
    </div>
    """

def _section_title(title: str, icon: str = ""):
    icon_html = f"{icon} " if icon else ""
    st.markdown(f"### {icon_html}{title}")

# ------------------------------------------------
# News (ORF)
# ------------------------------------------------

def _news_orf():
    _section_title("News", "📰")
    st.caption("Quelle: ORF News")
    try:
        import feedparser
        d = feedparser.parse("https://rss.orf.at/news.xml")
        if getattr(d, "bozo", 0):
            st.caption("RSS nicht verfügbar.")
            return
        for entry in (getattr(d, "entries", []) or [])[:5]:
            title = entry.get("title", "ohne Titel")
            link  = entry.get("link", None)
            if link:
                st.markdown(f"- [{title}]({link})")
            else:
                st.markdown(f"- {title}")
    except Exception:
        st.caption("RSS nicht verfügbar.")

# ------------------------------------------------
# Entry
# ------------------------------------------------

def render_start(username: str = "Gast"):
    # Deko/Toolbar/Pillen global ausblenden (kein sichtbares Artefakt über dem Header)
    st.markdown(
        """
        <style>
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stCloudAppStatus"],
        .stDeployButton,
        .viewerBadge_container__r3R7,
        .viewerBadge_link__qRIco,
        header [data-testid="stToolbar"],
        header [data-testid="stHeaderActionButtons"],
        header [data-testid="stActionButton"],
        button[title="Manage app"],
        button[title="View source"] { display:none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Header (schlank, ohne Box)
    st.markdown(f"### Willkommen, {username or 'Gast'} 👋")
    st.caption(f"{APP_NAME} v{APP_VERSION}")

    # User + Sicht
    urow = _fetch_user_row(username)
    functions = (urow[2] if urow else "") or ""
    units_str = (urow[3] if urow else "") or ""
    is_mgr = _is_admin_manager(functions)
    assigned = _decode_units(units_str)

    # Kennzahlen-Karten
    open_cnt, closed_cnt = _event_stats()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(_card_html("Abrechnungen – Status", "#3b82f6", [
            f"Offen: {open_cnt}",
            f"Abgeschlossen: {closed_cnt}",
        ]), unsafe_allow_html=True)

    # Letzter Umsatz je Bar (Global vs. eigene Bars)
    counts = _counts_from_meta()
    last_ev_id = _latest_closed_event_id()
    lines_bars: List[str] = []
    if counts["bars"] > 0:
        if is_mgr:
            # Admin/Betriebsleiter: alle Bars
            for i in range(1, counts["bars"] + 1):
                total = _sum_for_unit(last_ev_id, "bar", i)
                lines_bars.append(f"Bar {i}: {total:,.2f} €")
        else:
            # Leiter: nur eigene Bars
            own = assigned["bar"]
            if own:
                for i in own:
                    total = _sum_for_unit(last_ev_id, "bar", i)
                    lines_bars.append(f"Bar {i}: {total:,.2f} €")
            else:
                lines_bars.append("Keine Bars zugewiesen.")
    else:
        lines_bars.append("Keine Bars konfiguriert.")

    with c2:
        st.markdown(_card_html("Letzter Umsatz pro Bar", "#10b981", lines_bars), unsafe_allow_html=True)

    st.markdown("---")

    # Aktivitäten + News
    left, right = st.columns([2, 1])
    with left:
        _section_title("Letzte Aktivitäten", "🕑")
        with conn() as cn:
            c = cn.cursor()
            if not _table_exists(c, "audit_log"):
                st.caption("Noch keine Aktivitäten protokolliert.")
            else:
                rows = c.execute("""
                    SELECT ts, user, action, details
                      FROM audit_log
                     ORDER BY id DESC
                     LIMIT 8
                """).fetchall()
                if not rows:
                    st.caption("Noch keine Aktivitäten protokolliert.")
                else:
                    for ts, user, action, details in rows:
                        st.markdown(f"- `{ts}` · **{user or '—'}** · *{action}* — {details}")
    with right:
        _news_orf()
