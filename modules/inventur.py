# modules/inventur.py
import streamlit as st
import pandas as pd
import datetime
from typing import List, Dict, Any, Optional

from core.db import conn


# ------------------------------------------------------------
# DB-Hilfsfunktionen
# ------------------------------------------------------------

def _table_exists(cur, name: str) -> bool:
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _ensure_inventur_schema() -> None:
    """
    Stellt sicher, dass die Tabellen 'inventur' und 'inventur_items'
    mit allen benötigten Spalten existieren. Läuft idempotent.
    """
    with conn() as cn:
        c = cn.cursor()

        # --- inventur (Kopf) ---
        if not _table_exists(c, "inventur"):
            c.execute(
                """
                CREATE TABLE inventur (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    month       TEXT NOT NULL,              -- 'YYYY-MM'
                    created_at  TEXT NOT NULL,
                    created_by  TEXT,
                    status      TEXT NOT NULL,              -- draft|submitted|approved|rejected
                    reviewed_at TEXT,
                    reviewed_by TEXT,
                    note        TEXT
                )
                """
            )
        else:
            cols = {r[1] for r in c.execute("PRAGMA table_info(inventur)").fetchall()}

            def add_if_missing(col: str, ddl: str) -> None:
                if col not in cols:
                    c.execute(f"ALTER TABLE inventur ADD COLUMN {ddl}")

            add_if_missing("month",       "month       TEXT")
            add_if_missing("created_at",  "created_at  TEXT")
            add_if_missing("created_by",  "created_by  TEXT")
            add_if_missing("status",      "status      TEXT DEFAULT 'draft'")
            add_if_missing("reviewed_at", "reviewed_at TEXT")
            add_if_missing("reviewed_by", "reviewed_by TEXT")
            add_if_missing("note",        "note        TEXT")

        # --- inventur_items (Details) ---
        if not _table_exists(c, "inventur_items"):
            c.execute(
                """
                CREATE TABLE inventur_items (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    inventur_id    INTEGER NOT NULL,
                    item_id        INTEGER NOT NULL,
                    counted_qty    REAL NOT NULL DEFAULT 0,
                    purchase_price REAL,
                    total_value    REAL,
                    FOREIGN KEY(inventur_id) REFERENCES inventur(id)
                )
                """
            )
        else:
            cols = {r[1] for r in c.execute("PRAGMA table_info(inventur_items)").fetchall()}

            def add_if_missing(col: str, ddl: str) -> None:
                if col not in cols:
                    c.execute(f"ALTER TABLE inventur_items ADD COLUMN {ddl}")

            # Wichtig: alle neuen Spalten nachziehen
            add_if_missing("inventur_id",   "inventur_id    INTEGER NOT NULL DEFAULT 0")
            add_if_missing("item_id",       "item_id        INTEGER NOT NULL DEFAULT 0")
            add_if_missing("counted_qty",   "counted_qty    REAL NOT NULL DEFAULT 0")
            add_if_missing("purchase_price","purchase_price REAL")
            add_if_missing("total_value",   "total_value    REAL")

        # --- audit_log (für Änderungen) ---
        if not _table_exists(c, "audit_log"):
            c.execute(
                """
                CREATE TABLE audit_log (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts      TEXT NOT NULL,
                    user    TEXT,
                    action  TEXT,
                    details TEXT
                )
                """
            )

        cn.commit()


def _log(user: str, action: str, details: str) -> None:
    try:
        with conn() as cn:
            c = cn.cursor()
            c.execute(
                "INSERT INTO audit_log(ts, user, action, details) VALUES(?,?,?,?)",
                (
                    datetime.datetime.utcnow().isoformat(timespec="seconds"),
                    user or "",
                    action,
                    details,
                ),
            )
            cn.commit()
    except Exception:
        # Logging darf niemals die App zerlegen
        pass


# ------------------------------------------------------------
# Helper: Rechte / User-Infos
# ------------------------------------------------------------

def _current_user() -> str:
    return (st.session_state.get("username") or "").strip() or "unknown"


def _current_functions() -> str:
    return st.session_state.get("scope") or ""


def _is_admin() -> bool:
    role = (st.session_state.get("role") or "").lower()
    if role == "admin":
        return True
    funcs = [f.strip().lower() for f in _current_functions().split(",") if f.strip()]
    return ("admin" in funcs) or ("betriebsleiter" in funcs)


def _has_inventur_right() -> bool:
    if _is_admin():
        return True
    funcs = [f.strip().lower() for f in _current_functions().split(",") if f.strip()]
    return "inventur" in funcs


# ------------------------------------------------------------
# Helper: Artikel & Inventur-Daten
# ------------------------------------------------------------

def _load_items() -> pd.DataFrame:
    """
    Lädt Artikel aus der items-Tabelle.
    Versucht, gängige Spalten zu verwenden, ist aber robust bei älteren Schemas.
    Erwartete Spalten, wenn vorhanden:
      - id (Pflicht)
      - name / artikelname
      - unit / einheit
      - purchase_price / einkaufspreis
      - is_active
    """
    with conn() as cn:
        c = cn.cursor()
        # Schema ermitteln
        cols = [r[1] for r in c.execute("PRAGMA table_info(items)").fetchall()]
        if "id" not in cols:
            return pd.DataFrame()

        # Dynamisch Select-List bauen
        select_cols = ["id"]
        name_col = "name" if "name" in cols else ("artikelname" if "artikelname" in cols else None)
        if name_col:
            select_cols.append(f"{name_col} AS name")
        unit_col = "unit" if "unit" in cols else ("einheit" if "einheit" in cols else None)
        if unit_col:
            select_cols.append(f"{unit_col} AS unit")
        price_col = "purchase_price" if "purchase_price" in cols else ("einkaufspreis" if "einkaufspreis" in cols else None)
        if price_col:
            select_cols.append(f"{price_col} AS purchase_price")
        if "is_active" in cols:
            select_cols.append("is_active")

        sql = "SELECT " + ", ".join(select_cols) + " FROM items"
        if "is_active" in cols:
            sql += " WHERE COALESCE(is_active,1)=1"

        df = pd.read_sql(sql, cn)
        if "name" not in df.columns:
            df["name"] = "(ohne Name)"
        if "unit" not in df.columns:
            df["unit"] = ""
        if "purchase_price" not in df.columns:
            df["purchase_price"] = 0.0
        return df


def _get_or_create_current_inventur(user: str) -> Dict[str, Any]:
    """
    Liefert den Inventur-Kopfdatensatz für den aktuellen Monat (YYYY-MM).
    Legt bei Bedarf einen neuen mit status='draft' an.
    """
    now = datetime.date.today()
    month = now.strftime("%Y-%m")

    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            """
            SELECT id, month, created_at, created_by, status, reviewed_at, reviewed_by, note
              FROM inventur
             WHERE month=?
             ORDER BY datetime(created_at) DESC
             LIMIT 1
            """,
            (month,),
        ).fetchone()

        if row:
            return {
                "id": row[0],
                "month": row[1],
                "created_at": row[2],
                "created_by": row[3],
                "status": row[4],
                "reviewed_at": row[5],
                "reviewed_by": row[6],
                "note": row[7],
            }

        # Neu anlegen
        created_at = datetime.datetime.utcnow().isoformat(timespec="seconds")
        c.execute(
            """
            INSERT INTO inventur(month, created_at, created_by, status)
            VALUES(?,?,?,?)
            """,
            (month, created_at, user, "draft"),
        )
        inv_id = c.lastrowid
        cn.commit()

        _log(user, "inventur_create", f"Neue Inventur für {month} (id={inv_id}) angelegt")

        return {
            "id": inv_id,
            "month": month,
            "created_at": created_at,
            "created_by": user,
            "status": "draft",
            "reviewed_at": None,
            "reviewed_by": None,
            "note": "",
        }


def _load_inventur_items(inventur_id: int) -> pd.DataFrame:
    with conn() as cn:
        c = cn.cursor()
        df = pd.read_sql(
            """
            SELECT item_id, counted_qty, purchase_price, total_value
              FROM inventur_items
             WHERE inventur_id=?
            """,
            cn,
            params=(inventur_id,),
        )
    return df


def _save_inventur_items(inventur_id: int, username: str, edited_df: pd.DataFrame) -> None:
    with conn() as cn:
        c = cn.cursor()
        # Bestehende Einträge löschen & neu schreiben (einfach & robust)
        c.execute("DELETE FROM inventur_items WHERE inventur_id=?", (inventur_id,))
        rows = []
        for _, row in edited_df.iterrows():
            item_id = int(row["item_id"])
            qty = float(row.get("Gezählte Menge", 0) or row.get("counted_qty", 0) or 0)
            price = float(row.get("Einkaufspreis (€)", 0) or row.get("purchase_price", 0) or 0)
            total = qty * price
            rows.append((inventur_id, item_id, qty, price, total))
        c.executemany(
            """
            INSERT INTO inventur_items(inventur_id, item_id, counted_qty, purchase_price, total_value)
            VALUES(?,?,?,?,?)
            """,
            rows,
        )
        cn.commit()
    _log(username, "inventur_save", f"Inventur {inventur_id} gespeichert ({len(rows)} Positionen)")


def _update_status(inventur_id: int, new_status: str, username: str) -> None:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        if new_status in ("approved", "rejected"):
            c.execute(
                """
                UPDATE inventur
                   SET status=?,
                       reviewed_at=?,
                       reviewed_by=?
                 WHERE id=?
                """,
                (new_status, now, username, inventur_id),
            )
        else:
            c.execute(
                "UPDATE inventur SET status=? WHERE id=?",
                (new_status, inventur_id),
            )
        cn.commit()
    _log(username, "inventur_status", f"Inventur {inventur_id} Status → {new_status}")


def _list_inventuren() -> pd.DataFrame:
    with conn() as cn:
        df = pd.read_sql(
            """
            SELECT id, month, status, created_at, created_by, reviewed_at, reviewed_by
              FROM inventur
             ORDER BY month DESC, datetime(created_at) DESC
            """,
            cn,
        )
    return df


# ------------------------------------------------------------
# PDF Export
# ------------------------------------------------------------

def _export_pdf(inventur_id: int) -> Optional[bytes]:
    """
    Erstellt ein einfaches PDF mit den Inventur-Daten.
    Nutzt reportlab, falls vorhanden; sonst None.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        return None

    # Kopf & Positionen laden
    with conn() as cn:
        c = cn.cursor()
        head = c.execute(
            """
            SELECT month, created_at, created_by, status, reviewed_at, reviewed_by
              FROM inventur
             WHERE id=?
            """,
            (inventur_id,),
        ).fetchone()
        if not head:
            return None

        items = c.execute(
            """
            SELECT ii.counted_qty, ii.purchase_price, ii.total_value,
                   it.name
              FROM inventur_items ii
              JOIN items it ON it.id = ii.item_id
             WHERE ii.inventur_id=?
             ORDER BY it.name
            """,
            (inventur_id,),
        ).fetchall()

    month, created_at, created_by, status, reviewed_at, reviewed_by = head
    total_sum = sum((r[2] or 0) for r in items)

    from io import BytesIO
    buf = BytesIO()
    canv = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    y = height - 40
    canv.setFont("Helvetica-Bold", 14)
    canv.drawString(40, y, f"Inventur {month}")
    y -= 18
    canv.setFont("Helvetica", 10)
    canv.drawString(40, y, f"Erstellt am: {created_at or '-'} durch {created_by or '-'}")
    y -= 14
    canv.drawString(40, y, f"Status: {status}")
    y -= 14
    if reviewed_at or reviewed_by:
        canv.drawString(40, y, f"Freigabe: {reviewed_at or '-'} durch {reviewed_by or '-'}")
        y -= 14
    y -= 10

    canv.setFont("Helvetica-Bold", 10)
    canv.drawString(40, y, "Artikel")
    canv.drawString(260, y, "Menge")
    canv.drawString(320, y, "EK-Preis")
    canv.drawString(400, y, "Summe")
    y -= 12
    canv.line(40, y, width-40, y)
    y -= 14

    canv.setFont("Helvetica", 9)
    for r in items:
        qty, price, total, name = r
        if y < 60:
            canv.showPage()
            y = height - 40
            canv.setFont("Helvetica-Bold", 10)
            canv.drawString(40, y, "Artikel")
            canv.drawString(260, y, "Menge")
            canv.drawString(320, y, "EK-Preis")
            canv.drawString(400, y, "Summe")
            y -= 12
            canv.line(40, y, width-40, y)
            y -= 14
            canv.setFont("Helvetica", 9)

        canv.drawString(40, y, str(name))
        canv.drawRightString(300, y, f"{qty:.2f}")
        canv.drawRightString(380, y, f"{(price or 0):.2f} €")
        canv.drawRightString(470, y, f"{(total or 0):.2f} €")
        y -= 12

    y -= 16
    canv.setFont("Helvetica-Bold", 10)
    canv.drawRightString(470, y, f"Gesamtwert: {total_sum:.2f} €")

    canv.showPage()
    canv.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# ------------------------------------------------------------
# UI: Aktuelle Inventur
# ------------------------------------------------------------

def _render_current_inventur():
    user = _current_user()
    _ensure_inventur_schema()

    inv = _get_or_create_current_inventur(user)
    st.markdown(f"#### Inventur {inv['month']} ({inv['status']})")

    items_df = _load_items()
    if items_df.empty:
        st.info("Keine Artikel im Stammdatenbestand gefunden. Bitte zuerst im Admin-Cockpit Artikel importieren.")
        return

    # Bisherige Mengen holen
    existing = _load_inventur_items(inv["id"])
    existing_map = {int(r["item_id"]): r for _, r in existing.iterrows()} if not existing.empty else {}

    # DataFrame für Editor bauen
    df = pd.DataFrame({
        "item_id": items_df["id"].astype(int),
        "Artikel": items_df["name"],
        "Einheit": items_df.get("unit", ""),
        "Einkaufspreis (€)": items_df.get("purchase_price", 0.0).astype(float),
    })
    df["Gezählte Menge"] = df["item_id"].apply(
        lambda iid: float(existing_map.get(int(iid), {}).get("counted_qty", 0) or 0)
    )
    df["Warenwert (€)"] = df["Gezählte Menge"] * df["Einkaufspreis (€)"]
    total_value = df["Warenwert (€)"].sum()

    st.caption("Trage für jeden Artikel die physisch gezählte Menge ein und speichere die Inventur am Monatsende.")

    edited = st.data_editor(
    df,
    key="inv_items",
    column_config={
        "item_id": st.column_config.Column("item_id", disabled=True),  # FIXED
        "name": st.column_config.TextColumn("Artikel"),
        "counted_qty": st.column_config.NumberColumn("Gezählte Menge"),
        "purchase_price": st.column_config.NumberColumn("Einkaufspreis (€)"),
        "total_value": st.column_config.NumberColumn("Warenwert (€)"),
    },
    hide_index=True,
)

    # Warenwert neu berechnen
    edited["Warenwert (€)"] = edited["Gezählte Menge"].astype(float) * edited["Einkaufspreis (€)"].astype(float)
    total_value = edited["Warenwert (€)"].sum()

    st.markdown(f"**Gesamtwarenwert dieser Inventur:** {total_value:,.2f} €".replace(",", " ").replace(".", ","))

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💾 Inventur speichern", use_container_width=True):
            _save_inventur_items(inv["id"], user, edited)
            st.success("Inventur gespeichert.")
            st.rerun()
    with col2:
        if st.button("📤 Inventur einreichen (Review)", use_container_width=True):
            _save_inventur_items(inv["id"], user, edited)
            _update_status(inv["id"], "submitted", user)
            st.success("Inventur eingereicht. Ein Admin/Betriebsleiter muss diese freigeben.")
            st.rerun()
    with col3:
        if _is_admin() and st.button("✅ Inventur freigeben", use_container_width=True):
            _update_status(inv["id"], "approved", user)
            st.success("Inventur freigegeben.")
            st.rerun()


# ------------------------------------------------------------
# UI: Historie
# ------------------------------------------------------------

def _render_history():
    _ensure_inventur_schema()
    df = _list_inventuren()
    if df.empty:
        st.info("Noch keine Inventuren erfasst.")
        return

    st.markdown("#### Bisherige Inventuren")
    st.dataframe(
        df.rename(
            columns={
                "month": "Monat",
                "status": "Status",
                "created_at": "Erstellt am",
                "created_by": "Erstellt von",
                "reviewed_at": "Freigegeben am",
                "reviewed_by": "Freigegeben von",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    inv_ids = df["id"].tolist()
    labels = [f"{row['month']} · {row['status']} · #{row['id']}" for _, row in df.iterrows()]
    sel = st.selectbox("Inventur auswählen", options=inv_ids, format_func=lambda x: labels[inv_ids.index(x)])

    if sel:
        with conn() as cn:
            c = cn.cursor()
            head = c.execute(
                """
                SELECT month, status, created_at, created_by, reviewed_at, reviewed_by
                  FROM inventur
                 WHERE id=?
                """,
                (sel,),
            ).fetchone()
            items = pd.read_sql(
                """
                SELECT it.name AS Artikel,
                       ii.counted_qty AS Menge,
                       ii.purchase_price AS "Einkaufspreis (€)",
                       ii.total_value AS "Warenwert (€)"
                  FROM inventur_items ii
                  JOIN items it ON it.id = ii.item_id
                 WHERE ii.inventur_id=?
                 ORDER BY it.name
                """,
                cn,
                params=(sel,),
            )

        if head:
            month, status, created_at, created_by, reviewed_at, reviewed_by = head
            st.markdown(
                f"**Inventur {month}** – Status: `{status}`  \n"
                f"Erstellt am {created_at or '-'} durch {created_by or '-'}  \n"
                f"Freigabe: {reviewed_at or '-'} durch {reviewed_by or '-'}"
            )

        if items.empty:
            st.caption("Keine Positionen in dieser Inventur.")
        else:
            st.dataframe(items, use_container_width=True, hide_index=True)
            total = float(items["Warenwert (€)"].fillna(0).sum())
            st.markdown(f"**Gesamtwarenwert:** {total:,.2f} €".replace(",", " ").replace(".", ","))

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📄 PDF exportieren", use_container_width=True, key=f"pdf_{sel}"):
                pdf_bytes = _export_pdf(sel)
                if not pdf_bytes:
                    st.error("PDF-Export nicht möglich. Ist 'reportlab' installiert?")
                else:
                    st.download_button(
                        "Download PDF",
                        data=pdf_bytes,
                        file_name=f"inventur_{month.replace('-', '')}_{sel}.pdf",
                        mime="application/pdf",
                    )
        with col2:
            if _is_admin() and st.button("🔁 Status zurück auf 'draft'", use_container_width=True, key=f"reset_{sel}"):
                _update_status(sel, "draft", _current_user())
                st.success("Status zurück auf 'draft' gesetzt.")
                st.rerun()


# ------------------------------------------------------------
# Entry-Point
# ------------------------------------------------------------

def render_inventur(username: str = ""):
    """
    Wird von app.py aufgerufen.
    Sichtbar nur für Admins und Nutzer mit Funktion 'Inventur'.
    """
    if not _has_inventur_right():
        st.error("Kein Zugriff auf Inventur. Bitte Admin kontaktieren.")
        return

    st.markdown("### 📦 Monatsinventur")

    tabs = st.tabs(["Aktuelle Inventur", "Historie"])
    with tabs[0]:
        _render_current_inventur()
    with tabs[1]:
        _render_history()
