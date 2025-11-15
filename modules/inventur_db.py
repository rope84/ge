# modules/inventur_db.py
import datetime
from typing import List, Dict, Optional

import pandas as pd
from core.db import conn

# ---------------------------------------------------------
# Items vorhanden?
# ---------------------------------------------------------
def has_any_items() -> bool:
    """
    Prüft, ob überhaupt Artikel im Artikelstamm vorhanden sind.
    Nutzt die Tabelle 'items'.
    """
    with conn() as cn:
        c = cn.cursor()
        row = c.execute("SELECT COUNT(*) FROM items").fetchone()
    return bool(row and row[0] > 0)

# ---------------------------------------------------------
# Schema sicherstellen (NEUE Inventur-Tabellen)
# ---------------------------------------------------------
def ensure_inventur_schema() -> None:
    """
    Neue Inventur-Struktur:
    - inv_months  (Kopf pro Monat)
    - inv_items   (Positionen pro Artikel)
    """
    with conn() as cn:
        c = cn.cursor()

        # Kopf-Tabelle
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS inv_months (
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

        cols_head = {r[1] for r in c.execute("PRAGMA table_info(inv_months)").fetchall()}

        def _add_head(col: str, ddl: str) -> None:
            if col not in cols_head:
                c.execute(f"ALTER TABLE inv_months ADD COLUMN {ddl}")

        _add_head("status",       "status TEXT NOT NULL DEFAULT 'editing'")
        _add_head("created_at",   "created_at TEXT")
        _add_head("created_by",   "created_by TEXT")
        _add_head("submitted_at", "submitted_at TEXT")
        _add_head("submitted_by", "submitted_by TEXT")
        _add_head("approved_at",  "approved_at TEXT")
        _add_head("approved_by",  "approved_by TEXT")
        _add_head("updated_at",   "updated_at TEXT")

        # Positionen
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS inv_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inv_id INTEGER,
                item_id INTEGER,
                counted_qty REAL NOT NULL DEFAULT 0,
                purchase_price REAL NOT NULL DEFAULT 0,
                total_value REAL NOT NULL DEFAULT 0,
                updated_at TEXT,
                updated_by TEXT
            )
            """
        )

        cols_items = {r[1] for r in c.execute("PRAGMA table_info(inv_items)").fetchall()}

        def _add_it(col: str, ddl: str) -> None:
            if col not in cols_items:
                c.execute(f"ALTER TABLE inv_items ADD COLUMN {ddl}")

        _add_it("inv_id",         "inv_id INTEGER")
        _add_it("item_id",        "item_id INTEGER")
        _add_it("counted_qty",    "counted_qty REAL NOT NULL DEFAULT 0")
        _add_it("purchase_price", "purchase_price REAL NOT NULL DEFAULT 0")
        _add_it("total_value",    "total_value REAL NOT NULL DEFAULT 0")
        _add_it("updated_at",     "updated_at TEXT")
        _add_it("updated_by",     "updated_by TEXT")

        cn.commit()

# ---------------------------------------------------------
# Audit-Log
# ---------------------------------------------------------
def log_audit(username: str, action: str, details: str) -> None:
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
        pass

# ---------------------------------------------------------
# Betriebsname fürs UI
# ---------------------------------------------------------
def get_business_name() -> str:
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
    - auto_create=False: None, wenn keine existiert
    - auto_create=True: legt bei Bedarf eine neue Inventur in inv_months + inv_items an
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
              FROM inv_months
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
            INSERT INTO inv_months(
                year, month, status, created_at, created_by, updated_at
            )
            VALUES (?,?,?,?,?,?)
            """,
            (year, month, "editing", now, username, now),
        )
        inv_id = c.lastrowid

        # Artikelstamm → inv_items übernehmen
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
                INSERT INTO inv_items(
                    inv_id, item_id, counted_qty, purchase_price, total_value,
                    updated_at, updated_by
                )
                VALUES (?,?,?,?,?,?,?)
                """,
                rows,
            )

        cn.commit()

        log_audit(username, "inventur_create", f"year={year}, month={month}, inv_id={inv_id}")

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

def delete_inventur(inv_id: int, username: str) -> None:
    """
    Löscht eine Inventur + Positionen.
    """
    ensure_inventur_schema()
    with conn() as cn:
        c = cn.cursor()
        c.execute("DELETE FROM inv_items WHERE inv_id=?", (inv_id,))
        c.execute("DELETE FROM inv_months WHERE id=?", (inv_id,))
        cn.commit()
    log_audit(username, "inventur_delete", f"inv_id={inv_id}")

def load_inventur_items_df(inv_id: int) -> pd.DataFrame:
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
            FROM inv_items ii
            LEFT JOIN items it ON it.id = ii.item_id
            WHERE ii.inv_id = ?
            ORDER BY it.name COLLATE NOCASE
            """,
            cn,
            params=(inv_id,),
        )
    return df

def save_inventur_counts(
    inv_id: int, df: pd.DataFrame, username: str, submit: bool = False
) -> None:
    ensure_inventur_schema()
    now = datetime.datetime.now().isoformat(timespec="seconds")

    with conn() as cn:
        c = cn.cursor()

        for _, row in df.iterrows():
            item_id = int(row["item_id"])
            qty = float(row.get("counted_qty", 0) or 0)
            price = float(row.get("purchase_price", 0) or 0)
            total = qty * price

            c.execute(
                """
                UPDATE inv_items
                   SET counted_qty=?,
                       purchase_price=?,
                       total_value=?,
                       updated_at=?,
                       updated_by=?
                 WHERE inv_id=? AND item_id=?
                """,
                (qty, price, total, now, username, inv_id, item_id),
            )

        if submit:
            c.execute(
                """
                UPDATE inv_months
                   SET status='submitted',
                       submitted_at=?,
                       submitted_by=?,
                       updated_at=?
                 WHERE id=?
                """,
                (now, username, now, inv_id),
            )
            log_audit(username, "inventur_submit", f"inv_id={inv_id}")
        else:
            c.execute(
                """
                UPDATE inv_months
                   SET status='editing',
                       updated_at=?
                 WHERE id=?
                """,
                (now, inv_id),
            )
            log_audit(username, "inventur_save", f"inv_id={inv_id}")

        cn.commit()

def approve_inventur(inv_id: int, username: str) -> None:
    ensure_inventur_schema()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with conn() as cn:
        c = cn.cursor()
        c.execute(
            """
            UPDATE inv_months
               SET status='approved',
                   approved_at=?,
                   approved_by=?,
                   updated_at=?
             WHERE id=?
            """,
            (now, username, now, inv_id),
        )
        cn.commit()
    log_audit(username, "inventur_approve", f"inv_id={inv_id}")

def list_all_inventuren() -> List[Dict]:
    ensure_inventur_schema()
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            """
            SELECT id, year, month, status,
                   created_at, submitted_at, approved_at
              FROM inv_months
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

def get_inventur_total_value(inv_id: int) -> float:
    ensure_inventur_schema()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT SUM(total_value) FROM inv_items WHERE inv_id=?",
            (inv_id,),
        ).fetchone()
    return float(row[0] or 0.0)
