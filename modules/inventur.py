# modules/inventur.py
import calendar
import datetime
from typing import Optional

import streamlit as st

from core.config import APP_NAME, APP_VERSION
from modules import inventur_db as invdb  # relative Import aus modules/__init__.py


# ---------------------------------------------------------
# Rechte / Funktionen
# ---------------------------------------------------------
def _parse_functions(scope: str) -> list[str]:
    return [f.strip().lower() for f in (scope or "").split(",") if f.strip()]


def _has_inventur_right(role: str, scope: str) -> bool:
    """
    Admin & Betriebsleiter sehen immer Inventur.
    Zusätzlich jeder, dessen Functions 'inventur' enthält.
    """
    r = (role or "").lower()
    funcs = _parse_functions(scope)
    if r == "admin":
        return True
    if "admin" in funcs or "betriebsleiter" in funcs:
        return True
    if "inventur" in funcs or "inventur bearbeiten" in funcs:
        return True
    return False


# ---------------------------------------------------------
# UI-Helper
# ---------------------------------------------------------
def _inject_styles():
    st.markdown(
        """
        <style>
        .inv-hero {
            text-align: left;
            margin-bottom: 24px;
        }
        .inv-title {
            font-size: 1.6rem;
            font-weight: 700;
            color: #f9fafb;
            margin-bottom: 4px;
        }
        .inv-sub {
            font-size: .9rem;
            color: #e5e7eb;
            opacity: .8;
            margin-bottom: 2px;
        }
        .inv-mini {
            font-size: .78rem;
            color: #9ca3af;
            opacity: .8;
        }

        .inv-card {
            border-radius: 18px;
            padding: 18px 18px 14px 18px;
            background: radial-gradient(400px 220px at 0% 0%, rgba(56,189,248,0.18), transparent),
                        radial-gradient(600px 260px at 120% 0%, rgba(56,189,248,0.06), transparent),
                        rgba(15,23,42,0.96);
            box-shadow: 0 18px 45px rgba(0,0,0,0.55);
            border: 1px solid rgba(148,163,184,0.35);
        }

        .inv-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 0.75rem;
            border: 1px solid rgba(148,163,184,0.45);
            color: #e5e7eb;
            background: rgba(15,23,42,0.8);
            margin-bottom: 8px;
        }

        .inv-status-pill {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 500;
        }
        .inv-status-open {
            background: rgba(59,130,246,0.15);
            color: #bfdbfe;
            border: 1px solid rgba(59,130,246,0.55);
        }
        .inv-status-submitted {
            background: rgba(245,158,11,0.15);
            color: #fed7aa;
            border: 1px solid rgba(245,158,11,0.55);
        }
        .inv-status-approved {
            background: rgba(22,163,74,0.18);
            color: #bbf7d0;
            border: 1px solid rgba(22,163,74,0.55);
        }
        .inv-status-overdue {
            background: rgba(239,68,68,0.15);
            color: #fecaca;
            border: 1px solid rgba(239,68,68,0.6);
        }

        .inv-history-card {
            border-radius: 14px;
            padding: 10px 12px;
            margin-bottom: 8px;
            background: rgba(15,23,42,0.85);
            border: 1px solid rgba(55,65,81,0.8);
        }
        .inv-history-header {
            display:flex;
            justify-content:space-between;
            align-items:center;
            font-size:0.9rem;
            margin-bottom:2px;
        }
        .inv-history-meta {
            font-size:0.78rem;
            opacity:.75;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _status_pill(status: str, year: int, month: int) -> str:
    today = datetime.date.today()
    s = (status or "editing").lower()
    # Overdue-Logik: Monat liegt in der Vergangenheit und nicht freigegeben
    overdue = (year < today.year) or (year == today.year and month < today.month)
    if s == "approved":
        cls, label = "inv-status-approved", "Freigegeben"
    elif s == "submitted":
        cls, label = "inv-status-submitted", "Zur Freigabe eingereicht"
    elif overdue:
        cls, label = "inv-status-overdue", "Überfällig"
    else:
        cls, label = "inv-status-open", "In Bearbeitung"

    return f"<span class='inv-status-pill {cls}'>{label}</span>"


# ---------------------------------------------------------
# Aktuelle Inventur (Editor)
# ---------------------------------------------------------
def _render_current_inventur(username: str, is_reviewer: bool):
    """
    Zeigt/erstellt die Inventur für das aktuelle Monat.
    - normale User: Mengen eintragen, einreichen
    - Reviewer (Admin/Betriebsleiter): Überblick + ggf. Freigabe
    """
    today = datetime.date.today()
    month_label = calendar.month_name[today.month]

    # gibt None zurück, wenn noch keine Inventur existiert
    current_inv = invdb.get_current_inventur(auto_create=False, username=username)

    st.markdown("### Aktuelle Inventur")

    with st.container():
        st.markdown("<div class='inv-card'>", unsafe_allow_html=True)

        if not current_inv:
            st.markdown(
                f"**Noch keine Inventur für {month_label} {today.year} angelegt.**"
            )
            if st.button(
                f"📦 Inventur für {month_label} {today.year} starten",
                type="primary",
                use_container_width=True,
            ):
                current_inv = invdb.get_current_inventur(auto_create=True, username=username)
                st.success("Inventur angelegt. Artikel wurden aus dem Artikelstamm übernommen.")
                st.experimental_rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            return

        # Meta + Status
        status_html = _status_pill(current_inv["status"], current_inv["year"], current_inv["month"])
        st.markdown(
            f"""
            <div class="inv-history-header">
                <div>
                    <span class="inv-badge">Inventur {month_label} {current_inv['year']}</span>
                </div>
                <div>{status_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Daten laden
        df_items = invdb.load_inventur_items_df(current_inv["id"])

        if df_items.empty:
            st.caption("Keine Artikel gefunden. Bitte Artikelstamm im Admin-Cockpit prüfen.")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        # Nur Artikelname + Menge anzeigen; Preise laufen „unsichtbar“ mit.
        df_display = df_items.copy()

        st.caption("Bitte für alle Artikel die physisch gezählte Menge eintragen (0 ist erlaubt).")

        edited_df = st.data_editor(
            df_display,
            column_order=["item_name", "counted_qty"],
            column_config={
                "item_name": st.column_config.TextColumn("Artikel", disabled=True),
                "counted_qty": st.column_config.NumberColumn(
                    "Gezählte Menge", min_value=0.0, step=1.0
                ),
            },
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
        )

        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            save_btn = st.button("💾 Zwischenspeichern", use_container_width=True)
        with col2:
            submit_btn = st.button("✅ Inventur einreichen", use_container_width=True)
        with col3:
            approve_btn = False
            if is_reviewer and current_inv["status"] in ("submitted", "editing"):
                approve_btn = st.button("🔓 Inventur freigeben", use_container_width=True)

        if save_btn:
            invdb.save_inventur_counts(current_inv["id"], edited_df, username, submit=False)
            st.success("Inventur wurde zwischengespeichert.")
            st.experimental_rerun()

        if submit_btn:
            invdb.save_inventur_counts(current_inv["id"], edited_df, username, submit=True)
            st.success("Inventur eingereicht. Ein Betriebsleiter/Admin muss freigeben.")
            st.experimental_rerun()

        if approve_btn:
            invdb.save_inventur_counts(current_inv["id"], edited_df, username, submit=True)
            invdb.approve_inventur(current_inv["id"], username)
            st.success("Inventur wurde freigegeben.")
            st.experimental_rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------
# History / Rückblick
# ---------------------------------------------------------
def _render_history():
    st.markdown("### Inventur-Historie")

    all_inv = invdb.list_all_inventuren()
    if not all_inv:
        st.caption("Noch keine Inventuren vorhanden.")
        return

    today = datetime.date.today()

    for inv in all_inv:
        year = inv["year"]
        month = inv["month"]
        status = (inv["status"] or "editing").lower()
        month_label = calendar.month_abbr[month]

        total = invdb.get_inventur_total_value(inv["id"])

        # Farbe je nach Status
        overdue = (year < today.year) or (year == today.year and month < today.month)
        if status == "approved":
            pill_html = _status_pill(status, year, month)
        elif overdue:
            pill_html = _status_pill("overdue", year, month)
        else:
            pill_html = _status_pill(status, year, month)

        st.markdown(
            f"""
            <div class="inv-history-card">
              <div class="inv-history-header">
                <div><strong>{month_label} {year}</strong></div>
                <div>{pill_html}</div>
              </div>
              <div class="inv-history-meta">
                Wert gesamt: <strong>{total:,.2f} €</strong>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Details im Expander
        with st.expander(f"Details anzeigen – {month_label} {year}", expanded=False):
            df = invdb.load_inventur_items_df(inv["id"])
            st.dataframe(
                df[["item_name", "counted_qty", "purchase_price", "total_value"]],
                use_container_width=True,
            )
            # Optional: einfacher CSV-Export
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 CSV exportieren",
                data=csv,
                file_name=f"inventur_{year}_{month:02d}.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ---------------------------------------------------------
# Entry-Point für app.py
# ---------------------------------------------------------
def render_inventur(username: str = "unknown", role: str = "guest"):
    _inject_styles()

    scope = st.session_state.get("scope", "")
    if not _has_inventur_right(role, scope):
        st.error("Keine Berechtigung für die Inventur.")
        return

    club_name = invdb.get_business_name()

    st.markdown(
        f"""
        <div class="inv-hero">
          <div class="inv-title">Inventur · {club_name}</div>
          <div class="inv-sub">Monatliche Lagerbestandsaufnahme – schnell, simpel, nachvollziehbar.</div>
          <div class="inv-mini">{APP_NAME} · v{APP_VERSION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Layout: links aktuelle Inventur, rechts Historie
    left, right = st.columns([2, 1.4])

    is_reviewer = _has_inventur_right("admin", scope) or "betriebsleiter" in _parse_functions(scope)

    with left:
        _render_current_inventur(username, is_reviewer=is_reviewer)
    with right:
        _render_history()
