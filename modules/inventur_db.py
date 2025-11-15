# modules/inventur_db.py
import datetime
import sqlite3
from typing import List, Dict, Optional

import pandas as pd
from core.db import conn


def has_any_items() -> bool:
    """
    Prüft, ob überhaupt Artikel im Artikelstamm vorhanden sind.
    - Wenn es eine Spalte 'active' gibt, werden nur aktive gezählt.
    - Wenn nicht, werden alle Zeilen in 'items' gezählt.
    """
    with conn() as cn:
        c = cn.cursor()
        try:
            # Normalfall: items.active existiert
            row = c.execute(
                """
                SELECT COUNT(*)
                  FROM items
                 WHERE COALESCE(active, 1) = 1
                """
            ).fetchone()
        except sqlite3.OperationalError:
            # Fallback: keine active-Spalte -> alle Items zählen
            row = c.execute("SELECT COUNT(*) FROM items").fetchone()

    return bool(row and row[0] > 0)


def delete_inventur(inventur_id: int) -> None:
    """
    Löscht eine Inventur + zugehörige Positionen auf Basis des
    neuen Schemas:

      - Kopf:  inventur_months
      - Items: inventur_items
    """
    ensure_inventur_schema()
    with conn() as cn:
        c = cn.cursor()

        # Detailzeilen zuerst löschen
        c.execute(
            "DELETE FROM inventur_items WHERE inventur_id=?",
            (inventur_id,),
        )

        # Kopfzeile löschen
        c.execute(
            "DELETE FROM inventur_months WHERE id=?",
            (inventur_id,),
        )

        cn.commit()

    # Audit – wenn die Tabellen fehlen sollten, darf das nie crashen
    log_audit("system", "inventur_delete", f"inventur_id={inventur_id}")


# ---------------------------------------------------------
# Schema sicherstellen (Inventur-Tabellen)
# ---------------------------------------------------------
def ensure_inventur_schema() -> None:
    """
    Stellt sicher, dass die Tabellen für die Monatsinventur existieren
    und alle benötigten Spalten vorhanden sind.
    - inventur_months
    - inventur_items
    """
    with conn() as cn:
        c = cn.cursor()

        # Kopf-Tabelle für Monatsinventuren
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS inventur_months (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'editing',
                created_at TEXT,
                created_by TEXT,
                submitted_at TEXT,
                submitted_by TEXT,
                approved_at TEXT,
                approved_by TEXT,
                updated_at TEXT,
                UNIQUE(year, month)
            )
            """
        )

        cols_head = {r[1] for r in c.execute("PRAGMA table_info(inventur_months)").fetchall()}

        def _add_head(col: str, ddl: str) -> None:
            if col not in cols_head:
                c.execute(f"ALTER TABLE inventur_months ADD COLUMN {ddl}")

        _add_head("status", "status TEXT NOT NULL DEFAULT 'editing'")
        _add_head("created_at", "created_at TEXT")
        _add_head("created_by", "created_by TEXT")
        _add_head("submitted_at", "submitted_at TEXT")
        _add_head("submitted_by", "submitted_by TEXT")
        _add_head("approved_at", "approved_at TEXT")
        _add_head("approved_by", "approved_by TEXT")
        _add_head("updated_at", "updated_at TEXT")

        # Detail-Tabelle für Artikelmengen
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS inventur_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventur_id INTEGER,
                item_id INTEGER,
                counted_qty REAL NOT NULL DEFAULT 0,
                purchase_price REAL NOT NULL DEFAULT 0,
                total_value REAL NOT NULL DEFAULT 0,
                updated_at TEXT,
                updated_by TEXT
            )
            """
        )

        cols_items = {r[1] for r in c.execute("PRAGMA table_info(inventur_items)").fetchall()}

        def _add_it(col: str, ddl: str) -> None:
            if col not in cols_items:
                c.execute(f"ALTER TABLE inventur_items ADD COLUMN {ddl}")

        _add_it("inventur_id", "inventur_id INTEGER")
        _add_it("item_id", "item_id INTEGER")
        _add_it("counted_qty", "counted_qty REAL NOT NULL DEFAULT 0")
        _add_it("purchase_price", "purchase_price REAL NOT NULL DEFAULT 0")
        _add_it("total_value", "total_value REAL NOT NULL DEFAULT 0")
        _add_it("updated_at", "updated_at TEXT")
        _add_it("updated_by", "updated_by TEXT")

        cn.commit()


# ---------------------------------------------------------
# Helper: Audit-Log schreiben
# ---------------------------------------------------------
def log_audit(username: str, action: str, details: str) -> None:
    """
    Schreibt einen Eintrag in die bestehende audit_log-Tabelle,
    falls sie existiert.
    """
    ts = datetime.datetime.utcnow().isoformat(timespec="seconds")
    try:
        with conn() as cn:
            c = cn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    user TEXT,
                    action TEXT,
                    details TEXT
                )
                """
            )
            c.execute(
                "INSERT INTO audit_log(ts, user, action, details) VALUES (?,?,?,?)",
                (ts, username, action, details),
            )
            cn.commit()
    except Exception:
        # Audit darf nie die eigentliche Funktion killen
        pass


# ---------------------------------------------------------
# Helper: Business-Name (für UI)
# ---------------------------------------------------------
def get_business_name() -> str:
    """
    Liest den Betriebsnamen aus meta.business_name. Fallback: 'Gastro Essentials'.
    """
    try:
        with conn() as cn:
            c = cn.cursor()
            row = c.execute(
                "SELECT value FROM meta WHERE key='business_name'"
            ).fetchone()
        if row and (row[0] or "").strip():
            return row[0].strip()
    except Exception:
        pass
    return "Gastro Essentials"


# ---------------------------------------------------------
# Inventur-API
# ---------------------------------------------------------
def get_current_inventur(auto_create: bool, username: str) -> Optional[Dict]:
    """
    Liefert die Inventur für das aktuelle Monat.
    - auto_create=False: liefert None, wenn noch keine existiert
    - auto_create=True: legt bei Bedarf eine neue Inventur an und befüllt sie mit allen Artikeln aus items
    """
    ensure_inventur_schema()
    today = datetime.date.today()
    year, month = today.year, today.month

    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            """
            SELECT id, year, month, status, created_at, created_by,
                   submitted_at, submitted_by, approved_at, approved_by, updated_at
              FROM inventur_months
             WHERE year=? AND month=?
            """,
            (year, month),
        ).fetchone()

        if row:
            return {
                "id": row[0],
                "year": row[1],
                "month": row[2],
                "status": (row[3] or "editing"),
                "created_at": row[4] or "",
                "created_by": row[5] or "",
                "submitted_at": row[6] or "",
                "submitted_by": row[7] or "",
                "approved_at": row[8] or "",
                "approved_by": row[9] or "",
                "updated_at": row[10] or "",
            }

        if not auto_create:
            return None

        # Neue Inventur anlegen
        now = datetime.datetime.now().isoformat(timespec="seconds")
        c.execute(
            """
            INSERT INTO inventur_months(
                year, month, status, created_at, created_by, updated_at
            )
            VALUES (?,?,?,?,?,?)
            """,
            (year, month, "editing", now, username, now),
        )
        inv_id = c.lastrowid

        # Artikelstamm in inventur_items übernehmen
        items = c.execute(
            "SELECT id, name, purchase_price FROM items ORDER BY name COLLATE NOCASE"
        ).fetchall()

        rows = []
        for item_id, name, price in items:
            price = float(price or 0)
            rows.append(
                (
                    inv_id,
                    item_id,
                    0.0,    # counted_qty
                    price,  # purchase_price
                    0.0,    # total_value
                    now,
                    username,
                )
            )

        if rows:
            c.executemany(
                """
                INSERT INTO inventur_items(
                    inventur_id, item_id, counted_qty, purchase_price, total_value,
                    updated_at, updated_by
                )
                VALUES (?,?,?,?,?,?,?)
                """,
                rows,
            )

        cn.commit()

        log_audit(username, "inventur_create", f"year={year}, month={month}, inventur_id={inv_id}")

        return {
            "id": inv_id,
            "year": year,
            "month": month,
            "status": "editing",
            "created_at": now,
            "created_by": username,
            "submitted_at": "",
            "submitted_by": "",
            "approved_at": "",
            "approved_by": "",
            "updated_at": now,
        }


def load_inventur_items_df(inventur_id: int) -> pd.DataFrame:
    """
    Lädt alle Artikelzeilen einer Inventur inkl. Artikelnamen.
    """
    ensure_inventur_schema()
    with conn() as cn:
        df = pd.read_sql(
            """
            SELECT
                ii.item_id,
                it.name AS item_name,
                ii.counted_qty,
                ii.purchase_price,
                ii.total_value
            FROM inventur_items ii
            LEFT JOIN items it ON it.id = ii.item_id
            WHERE ii.inventur_id = ?
            ORDER BY it.name COLLATE NOCASE
            """,
            cn,
            params=(inventur_id,),
        )
    return df


def save_inventur_counts(
    inventur_id: int, df: pd.DataFrame, username: str, submit: bool = False
) -> None:
    """
    Speichert gezählte Mengen + berechnet total_value.
    submit=True markiert die Inventur als 'submitted' (zur Freigabe).
    """
    ensure_inventur_schema()
    now = datetime.datetime.now().isoformat(timespec="seconds")

    with conn() as cn:
        c = cn.cursor()

        # Pro Zeile: Menge & Preis übernehmen
        for _, row in df.iterrows():
            item_id = int(row["item_id"])
            qty = float(row.get("counted_qty", 0) or 0)
            price = float(row.get("purchase_price", 0) or 0)
            total = qty * price

            c.execute(
                """
                UPDATE inventur_items
                   SET counted_qty=?,
                       purchase_price=?,
                       total_value=?,
                       updated_at=?,
                       updated_by=?
                 WHERE inventur_id=? AND item_id=?
                """,
                (qty, price, total, now, username, inventur_id, item_id),
            )

        # Kopf-Status
        if submit:
            c.execute(
                """
                UPDATE inventur_months
                   SET status='submitted',
                       submitted_at=?,
                       submitted_by=?,
                       updated_at=?
                 WHERE id=?
                """,
                (now, username, now, inventur_id),
            )
            log_audit(username, "inventur_submit", f"inventur_id={inventur_id}")
        else:
            c.execute(
                """
                UPDATE inventur_months
                   SET status='editing',
                       updated_at=?
                 WHERE id=?
                """,
                (now, inventur_id),
            )
            log_audit(username, "inventur_save", f"inventur_id={inventur_id}")

        cn.commit()


def approve_inventur(inventur_id: int, username: str) -> None:
    """
    Admin/Betriebsleiter gibt eine Inventur frei.
    """
    ensure_inventur_schema()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        c.execute(
            """
            UPDATE inventur_months
               SET status='approved',
                   approved_at=?,
                   approved_by=?,
                   updated_at=?
             WHERE id=?
            """,
            (now, username, now, inventur_id),
        )
        cn.commit()
    log_audit(username, "inventur_approve", f"inventur_id={inventur_id}")


def list_all_inventuren() -> List[Dict]:
    """
    Liste aller Inventuren (für History / Überblick).
    """
    ensure_inventur_schema()
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            """
            SELECT id, year, month, status,
                   created_at, submitted_at, approved_at
              FROM inventur_months
             ORDER BY year DESC, month DESC
            """
        ).fetchall()

    out: List[Dict] = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "year": r[1],
                "month": r[2],
                "status": (r[3] or "editing"),
                "created_at": r[4] or "",
                "submitted_at": r[5] or "",
                "approved_at": r[6] or "",
            }
        )
    return out


def get_inventur_total_value(inventur_id: int) -> float:
    """
    Summe total_value für eine Inventur.
    """
    ensure_inventur_schema()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT SUM(total_value) FROM inventur_items WHERE inventur_id=?",
            (inventur_id,),
        ).fetchone()
    return float(row[0] or 0.0)
