# modules/admin.py
import datetime
from typing import List, Dict

import pandas as pd
import streamlit as st

from core.db import conn
from core.config import APP_NAME, APP_VERSION
from core import auth as auth_mod
from . import inventur_db as invdb


# ---------------------------------------------------------
# Styles
# ---------------------------------------------------------
def _inject_admin_styles():
    st.markdown(
        """
        <style>
        /* Admin-Hero */
        .admin-hero {
            margin-bottom: 18px;
        }
        .admin-title {
            font-size: 1.7rem;
            font-weight: 700;
            color: #f9fafb;
            margin-bottom: 4px;
        }
        .admin-sub {
            font-size: .9rem;
            color: #e5e7eb;
            opacity: .8;
            margin-bottom: 2px;
        }
        .admin-mini {
            font-size: .78rem;
            color: #9ca3af;
            opacity: .8;
        }

        /* Karten */
        .admin-card {
            border-radius: 16px;
            padding: 14px 16px 12px 16px;
            background: rgba(15,23,42,0.96);
            border: 1px solid rgba(148,163,184,0.4);
            box-shadow: 0 16px 40px rgba(0,0,0,0.55);
            margin-bottom: 12px;
        }

        .admin-pill {
            display:inline-block;
            padding: 2px 10px;
            border-radius: 999px;
            font-size: .75rem;
            border:1px solid rgba(148,163,184,.5);
            color:#e5e7eb;
            background: rgba(15,23,42,0.9);
        }

        .admin-status-pill {
            display:inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: .75rem;
            font-weight: 500;
        }
        .admin-status-editing {
            background: rgba(59,130,246,0.15);
            color: #bfdbfe;
            border: 1px solid rgba(59,130,246,0.6);
        }
        .admin-status-submitted {
            background: rgba(245,158,11,0.15);
            color: #fed7aa;
            border: 1px solid rgba(245,158,11,0.6);
        }
        .admin-status-approved {
            background: rgba(22,163,74,0.18);
            color: #bbf7d0;
            border: 1px solid rgba(22,163,74,0.6);
        }
        .admin-status-overdue {
            background: rgba(239,68,68,0.18);
            color: #fecaca;
            border: 1px solid rgba(239,68,68,0.6);
        }

        .admin-history-row {
            padding: 6px 0;
            border-bottom: 1px solid rgba(55,65,81,0.7);
            font-size: .88rem;
        }
        .admin-history-row:last-child {
            border-bottom: none;
        }

        /* Toolbar / Deploy-Pillen ausblenden (wie beim Login) */
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stCloudAppStatus"],
        header [data-testid="stToolbar"],
        header [data-testid="stHeaderActionButtons"],
        header [data-testid="stActionButton"],
        .stDeployButton,
        .viewerBadge_container__r3R7,
        button[title="Manage app"],
        button[title="View source"],
        div[style*="linear-gradient"][style*="999px"],
        div[style*="linear-gradient"][style*="border-radius: 999px"],
        div[style*="linear-gradient"][style*="border-radius:999px"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# Helper
# ---------------------------------------------------------
def _inventur_status_pill(inv: Dict) -> str:
    today = datetime.date.today()
    year = inv["year"]
    month = inv["month"]
    status = (inv["status"] or "editing").lower()
    overdue = (year < today.year) or (year == today.year and month < today.month)

    if status == "approved":
        cls, label = "admin-status-approved", "Freigegeben"
    elif status == "submitted":
        cls, label = "admin-status-submitted", "Zur Freigabe eingereicht"
    elif overdue and status != "approved":
        cls, label = "admin-status-overdue", "Überfällig"
    else:
        cls, label = "admin-status-editing", "In Bearbeitung"

    return f"<span class='admin-status-pill {cls}'>{label}</span>"


# ---------------------------------------------------------
# Sektion: Betrieb (nur grob – Name etc.)
# ---------------------------------------------------------
def _render_section_betrieb():
    st.subheader("Betriebseinstellungen")

    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT value FROM meta WHERE key='business_name'"
        ).fetchone()
        business_name = (row[0] if row and row[0] else "").strip()

    new_name = st.text_input("Name des Betriebs", value=business_name, placeholder="z.B. O - der Klub")

    if st.button("Speichern", type="primary"):
        with conn() as cn:
            c = cn.cursor()
            c.execute(
                """
                INSERT INTO meta(key, value)
                VALUES('business_name', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (new_name.strip(),),
            )
            cn.commit()
        st.success("Betriebsname gespeichert.")


# ---------------------------------------------------------
# Sektion: Artikel (generische Bearbeitung items)
# ---------------------------------------------------------
def _render_section_artikel():
    st.subheader("Artikelstamm")

    try:
        with conn() as cn:
            df = pd.read_sql("SELECT * FROM items ORDER BY name COLLATE NOCASE", cn)
    except Exception as e:
        st.error(f"Artikel konnten nicht geladen werden: {e}")
        return

    if df.empty:
        st.info("Noch keine Artikel vorhanden. Import oder Anlage im Admin-Cockpit erforderlich.")
        return

    st.caption("Hinweis: Spalten sind generisch. Wichtig für Inventur sind mindestens 'id', 'name', 'purchase_price'.")

    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
    )

    if st.button("Änderungen speichern", type="primary", use_container_width=True):
        try:
            with conn() as cn:
                c = cn.cursor()
                cols = list(edited.columns)
                pk_col = "id"
                if pk_col not in cols:
                    st.error("Es wird eine 'id'-Spalte als Primärschlüssel erwartet.")
                    return

                cols_no_id = [c2 for c2 in cols if c2 != pk_col]
                set_clause = ", ".join(f"{c2}=?" for c2 in cols_no_id)

                for _, row in edited.iterrows():
                    params = [row[c2] for c2 in cols_no_id]
                    params.append(int(row[pk_col]))
                    c.execute(
                        f"UPDATE items SET {set_clause} WHERE {pk_col}=?",
                        params,
                    )
                cn.commit()
            st.success("Artikel gespeichert.")
        except Exception as e:
            st.error(f"Fehler beim Speichern der Artikel: {e}")


# ---------------------------------------------------------
# Sektion: Inventuren (Admin-Overview)
# ---------------------------------------------------------
def _render_section_inventuren():
    st.subheader("Inventuren – Übersicht & Freigabe")

    all_inv = invdb.list_all_inventuren()
    if not all_inv:
        st.info("Noch keine Inventuren vorhanden.")
        return

    username = st.session_state.get("username", "") or "admin"

    # Auswahl-Box für Detail-Edit
    inv_options = {
        f"{inv['year']}-{inv['month']:02d} ({inv['status']})": inv["id"]
        for inv in all_inv
    }

    st.markdown("<div class='admin-card'>", unsafe_allow_html=True)
    st.markdown("**Alle Inventuren**", unsafe_allow_html=True)

    for inv in all_inv:
        label = f"{inv['year']}-{inv['month']:02d}"
        pill_html = _inventur_status_pill(inv)
        total = invdb.get_inventur_total_value(inv["id"])
        colL, colR = st.columns([3, 2])
        with colL:
            st.markdown(
                f"""
                <div class="admin-history-row">
                    <strong>{label}</strong><br>
                    <span style="font-size:.8rem;opacity:.7">Wert gesamt: {total:,.2f} €</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with colR:
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("Bearbeiten", key=f"inv_edit_{inv['id']}"):
                    st.session_state["admin_inv_edit_id"] = inv["id"]
            with b2:
                if st.button("Freigeben", key=f"inv_approve_{inv['id']}"):
                    invdb.approve_inventur(inv["id"], username)
                    st.success(f"Inventur {label} freigegeben.")
                    st.rerun()
            with b3:
                if st.button("Löschen", key=f"inv_del_{inv['id']}"):
                    invdb.delete_inventur(inv["id"])
                    st.warning(f"Inventur {label} gelöscht.")
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # Detail-Editor, falls Inventur ausgewählt
    edit_id = st.session_state.get("admin_inv_edit_id")
    if edit_id:
        st.markdown("---")
        st.markdown(f"### Inventur bearbeiten – ID {edit_id}")

        df = invdb.load_inventur_items_df(edit_id)
        if df.empty:
            st.caption("Keine Positionen vorhanden (evtl. leerer Artikelstamm zur Zeit der Inventur).")
        else:
            st.caption("Mengen können hier angepasst werden. Werte werden automatisch neu berechnet.")
            edited_df = st.data_editor(
                df,
                column_order=["item_name", "counted_qty", "purchase_price", "total_value"],
                column_config={
                    "item_name": st.column_config.TextColumn("Artikel", disabled=True),
                    "counted_qty": st.column_config.NumberColumn(
                        "Gezählte Menge", min_value=0.0, step=1.0
                    ),
                    "purchase_price": st.column_config.NumberColumn(
                        "EK Netto", min_value=0.0
                    ),
                    "total_value": st.column_config.NumberColumn(
                        "Gesamtwert", disabled=True
                    ),
                },
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Änderungen speichern", use_container_width=True, key="admin_inv_save"):
                    invdb.save_inventur_counts(edit_id, edited_df, username, submit=False)
                    st.success("Inventur gespeichert.")
                    st.rerun()
            with col2:
                if st.button("✅ Speichern & freigeben", use_container_width=True, key="admin_inv_save_approve"):
                    invdb.save_inventur_counts(edit_id, edited_df, username, submit=True)
                    invdb.approve_inventur(edit_id, username)
                    st.success("Inventur gespeichert und freigegeben.")
                    st.rerun()

            st.download_button(
                "📥 CSV exportieren",
                data=edited_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"inventur_admin_{edit_id}.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ---------------------------------------------------------
# Sektion: Benutzer (ohne zweite Navigation)
# ---------------------------------------------------------
def _render_section_users():
    st.subheader("Benutzerverwaltung")

    pending_count = 0
    try:
        pending_count = auth_mod.pending_count()
    except Exception:
        pass

    if pending_count:
        st.caption(f"🔔 Es gibt {pending_count} offene Registrierungsanfragen.")

    # Pending-Queue (Registrierungen)
    with st.expander("Offene Registrierungen anzeigen / bearbeiten", expanded=False):
        try:
            pendings = auth_mod.list_pending_users()
        except Exception as e:
            st.error(f"Pending-User konnten nicht geladen werden: {e}")
            pendings = []

        if not pendings:
            st.caption("Keine offenen Registrierungen.")
        else:
            for u in pendings:
                colL, colR = st.columns([3, 2])
                with colL:
                    st.markdown(
                        f"**{u['username']}** – {u['first_name']} {u['last_name']}  \n"
                        f"<span style='font-size:.8rem;opacity:.7'>{u['email']} – registriert am {u['created_at']}</span>",
                        unsafe_allow_html=True,
                    )
                with colR:
                    fn = st.text_input(
                        "Funktionen (z.B. admin,inventur)",
                        key=f"fn_{u['username']}",
                        placeholder="admin,inventur",
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Freigeben", key=f"approve_{u['username']}"):
                            ok, msg = auth_mod.approve_user(u["username"], fn)
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                    with c2:
                        if st.button("Löschen", key=f"reject_{u['username']}"):
                            ok, msg = auth_mod.reject_user(u["username"])
                            if ok:
                                st.warning(msg)
                                st.rerun()
                            else:
                                st.error(msg)

    st.markdown("---")

    # Aktive Benutzer Tabelle
    st.markdown("**Aktive Benutzer & Rollen**")

    with conn() as cn:
        df = pd.read_sql(
            """
            SELECT id, username,
                   COALESCE(first_name,'') AS first_name,
                   COALESCE(last_name,'')  AS last_name,
                   COALESCE(email,'')      AS email,
                   COALESCE(functions,'')  AS functions,
                   COALESCE(status,'active') AS status
              FROM users
             ORDER BY username
            """,
            cn,
        )

    if df.empty:
        st.info("Noch keine Benutzer vorhanden.")
        return

    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "username": st.column_config.TextColumn("Benutzername", disabled=True),
            "first_name": st.column_config.TextColumn("Vorname"),
            "last_name": st.column_config.TextColumn("Nachname"),
            "email": st.column_config.TextColumn("E-Mail"),
            "functions": st.column_config.TextColumn("Funktionen (Komma-getrennt)"),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["active", "pending", "disabled"],
            ),
        },
    )

    if st.button("Änderungen speichern", type="primary", use_container_width=True, key="admin_users_save"):
        try:
            with conn() as cn:
                c = cn.cursor()
                for _, row in edited.iterrows():
                    c.execute(
                        """
                        UPDATE users
                           SET first_name=?,
                               last_name=?,
                               email=?,
                               functions=?,
                               status=?
                         WHERE id=?
                        """,
                        (
                            row["first_name"] or "",
                            row["last_name"] or "",
                            row["email"] or "",
                            row["functions"] or "",
                            (row["status"] or "active").lower(),
                            int(row["id"]),
                        ),
                    )
                cn.commit()
            st.success("Benutzer aktualisiert.")
        except Exception as e:
            st.error(f"Fehler beim Speichern der Benutzer: {e}")


# ---------------------------------------------------------
# Entry-Point für app.py
# ---------------------------------------------------------
def render_admin():
    """
    Wird von app.py (route()) ohne Argumente aufgerufen.
    """
    _inject_admin_styles()

    st.markdown(
        f"""
        <div class="admin-hero">
          <div class="admin-title">Admin-Cockpit</div>
          <div class="admin-sub">Zentrale Verwaltung von Betrieb, Artikeln, Inventuren & Benutzern.</div>
          <div class="admin-mini">{APP_NAME} · v{APP_VERSION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Haupt-Navigation innerhalb des Admin-Cockpits
    # Reihenfolge wie gewünscht: Import – Kategorien – Artikel – Inventuren – Benutzer
    tab_choice = st.radio(
        "Bereich",
        ["Betrieb", "Artikel", "Inventuren", "Benutzer"],
        horizontal=True,
        label_visibility="collapsed",
        key="admin_section_choice",
    )

    if tab_choice == "Betrieb":
        _render_section_betrieb()
    elif tab_choice == "Artikel":
        _render_section_artikel()
    elif tab_choice == "Inventuren":
        _render_section_inventuren()
    elif tab_choice == "Benutzer":
        _render_section_users()
