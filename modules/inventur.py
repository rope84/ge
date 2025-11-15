# modules/inventur_db.py
import datetime
from typing import Optional, List, Dict

import pandas as pd
from core.db import conn


# ---------------------------------------------------------
# Schema-Helfer
# ---------------------------------------------------------
def _ensure_schema() -> None:
    """
    Stellt sicher, dass die Tabellen für Inventur existieren
    und alle benötigten Spalten haben (inkl. jahr/monat in inventur_items).
    """
    with conn() as cn:
        c = cn.cursor()

        # Haupttabelle für Inventuren
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS inventur (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL DEFAULT 0,
                month INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'editing',
                created_by TEXT,
                created_at TEXT,
                submitted_by TEXT,
                submitted_at TEXT,
                approved_by TEXT,
                approved_at TEXT
            )
            """
        )

        # Items je Inventur
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS inventur_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventur_id INTEGER NOT NULL,
                item_id INTEGER,
                item_name TEXT NOT NULL,
                counted_qty REAL NOT NULL DEFAULT 0,
                purchase_price REAL NOT NULL DEFAULT 0,
                total_value REAL NOT NULL DEFAULT 0,
                jahr INTEGER NOT NULL DEFAULT 0,
                monat INTEGER NOT NULL DEFAULT 0,
                changed_by TEXT,
                changed_at TEXT
            )
            """
        )

        # Meta-Tabelle (für Betriebsname etc.)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        # Bestehende Spalten prüfen & ggf. ergänzen (robust bei älteren DBs)
        def _add_column(table: str, col: str, ddl: str):
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

        # Inventur-Spalten absichern
        _add_column("inventur", "year", "year INTEGER NOT NULL DEFAULT 0")
        _add_column("inventur", "month", "month INTEGER NOT NULL DEFAULT 0")
        _add_column("inventur", "status", "status TEXT NOT NULL DEFAULT 'editing'")
        _add_column("inventur", "created_by", "created_by TEXT")
        _add_column("inventur", "created_at", "created_at TEXT")
        _add_column("inventur", "submitted_by", "submitted_by TEXT")
        _add_column("inventur", "submitted_at", "submitted_at TEXT")
        _add_column("inventur", "approved_by", "approved_by TEXT")
        _add_column("inventur", "approved_at", "approved_at TEXT")

        # Inventur-Items Spalten absichern (insb. jahr/monat!)
        _add_column("inventur_items", "inventur_id", "inventur_id INTEGER NOT NULL DEFAULT 0")
        _add_column("inventur_items", "item_id", "item_id INTEGER")
        _add_column("inventur_items", "item_name", "item_name TEXT NOT NULL DEFAULT ''")
        _add_column("inventur_items", "counted_qty", "counted_qty REAL NOT NULL DEFAULT 0")
        _add_column("inventur_items", "purchase_price", "purchase_price REAL NOT NULL DEFAULT 0")
        _add_column("inventur_items", "total_value", "total_value REAL NOT NULL DEFAULT 0")
        _add_column("inventur_items", "jahr", "jahr INTEGER NOT NULL DEFAULT 0")
        _add_column("inventur_items", "monat", "monat INTEGER NOT NULL DEFAULT 0")
        _add_column("inventur_items", "changed_by", "changed_by TEXT")
        _add_column("inventur_items", "changed_at", "changed_at TEXT")

        # Backfill: keine NULLs, damit NOT NULL nicht kracht
        c.execute("UPDATE inventur_items SET jahr  = COALESCE(jahr, 0)")
        c.execute("UPDATE inventur_items SET monat = COALESCE(monat, 0)")
        c.execute("UPDATE inventur_items SET counted_qty   = COALESCE(counted_qty, 0)")
        c.execute("UPDATE inventur_items SET purchase_price= COALESCE(purchase_price, 0)")
        c.execute("UPDATE inventur_items SET total_value   = COALESCE(total_value, 0)")

        cn.commit()


# ---------------------------------------------------------
# Hilfen: Betriebsname
# ---------------------------------------------------------
def get_business_name() -> str:
    _ensure_schema()
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
# Artikelstamm laden (für erste Inventur)
# ---------------------------------------------------------
def _load_master_items(c) -> List[tuple]:
    """
    Versucht den Artikelstamm zu laden.
    Gibt Liste von Tuples (item_id, item_name, purchase_price) zurück.
    Versucht mehrere mögliche Tabellennamen/Spalten – bricht aber nicht die App,
    wenn nichts gefunden wird.
    """
    candidates = [
        # (sql, description)
        ("SELECT id, name, einkaufspreis FROM items", "items (name/einkaufspreis)"),
        ("SELECT id, name, purchase_price FROM items", "items (purchase_price)"),
        ("SELECT id, artikelname, einkaufspreis FROM artikel", "artikel (artikelname/einkaufspreis)"),
    ]
    for sql, _desc in candidates:
        try:
            rows = c.execute(sql).fetchall()
            if rows:
                return rows
        except Exception:
            continue
    return []


# ---------------------------------------------------------
# Inventur: aktueller Monat
# ---------------------------------------------------------
def get_current_inventur(auto_create: bool, username: str) -> Optional[Dict]:
    """
    Holt (und optional erstellt) die Inventur des aktuellen Monats.
    Rückgabe: Dict mit keys: id, year, month, status, created_by, created_at, ...
    """
    _ensure_schema()
    today = datetime.date.today()
    year, month = today.year, today.month
    now = datetime.datetime.utcnow().isoformat()

    with conn() as cn:
        c = cn.cursor()

        # Gibt es schon eine Inventur für diesen Monat?
        row = c.execute(
            """
            SELECT id, year, month, status, created_by, created_at,
                   submitted_by, submitted_at, approved_by, approved_at
              FROM inventur
             WHERE year=? AND month=?
             LIMIT 1
            """,
            (year, month),
        ).fetchone()

        if row:
            return {
                "id": row[0],
                "year": row[1],
                "month": row[2],
                "status": row[3],
                "created_by": row[4],
                "created_at": row[5],
                "submitted_by": row[6],
                "submitted_at": row[7],
                "approved_by": row[8],
                "approved_at": row[9],
            }

        if not auto_create:
            return None

        # Neue Inventur anlegen
        c.execute(
            """
            INSERT INTO inventur(year, month, status, created_by, created_at)
            VALUES(?,?,?,?,?)
            """,
            (year, month, "editing", username or "", now),
        )
        inv_id = c.lastrowid

        # Items aus Artikelstamm übernehmen
        master_items = _load_master_items(c)

        rows = []
        for item_id, item_name, purchase_price in master_items:
            pp = float(purchase_price or 0)
            rows.append(
                (
                    inv_id,
                    int(item_id),
                    str(item_name or ""),
                    0.0,           # counted_qty
                    pp,            # purchase_price
                    0.0,           # total_value
                    year,
                    month,
                    username or "",
                    now,
                )
            )

        if rows:
            c.executemany(
                """
                INSERT INTO inventur_items(
                    inventur_id,
                    item_id,
                    item_name,
                    counted_qty,
                    purchase_price,
                    total_value,
                    jahr,
                    monat,
                    changed_by,
                    changed_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )

        cn.commit()

        return {
            "id": inv_id,
            "year": year,
            "month": month,
            "status": "editing",
            "created_by": username or "",
            "created_at": now,
            "submitted_by": None,
            "submitted_at": None,
            "approved_by": None,
            "approved_at": None,
        }


# ---------------------------------------------------------
# Items einer Inventur laden (für UI)
# ---------------------------------------------------------
def load_inventur_items_df(inventur_id: int) -> pd.DataFrame:
    _ensure_schema()
    with conn() as cn:
        df = pd.read_sql(
            """
            SELECT
                id,
                inventur_id,
                item_id,
                item_name,
                counted_qty,
                purchase_price,
                total_value,
                jahr,
                monat
              FROM inventur_items
             WHERE inventur_id=?
             ORDER BY item_name COLLATE NOCASE
            """,
            cn,
            params=(inventur_id,),
        )
    return df


# ---------------------------------------------------------
# Inventur-Werte speichern / einreichen
# ---------------------------------------------------------
def save_inventur_counts(
    inventur_id: int,
    df_items: pd.DataFrame,
    username: str,
    submit: bool = False,
) -> None:
    _ensure_schema()
    now = datetime.datetime.utcnow().isoformat()

    with conn() as cn:
        c = cn.cursor()

        # Für jede Zeile total_value berechnen & updaten
        for _, row in df_items.iterrows():
            item_row_id = int(row["id"])
            qty = float(row.get("counted_qty", 0) or 0)
            price = float(row.get("purchase_price", 0) or 0)
            total = qty * price

            c.execute(
                """
                UPDATE inventur_items
                   SET counted_qty=?,
                       purchase_price=?,
                       total_value=?,
                       changed_by=?,
                       changed_at=?
                 WHERE id=? AND inventur_id=?
                """,
                (qty, price, total, username or "", now, item_row_id, inventur_id),
            )

        # Status der Inventur anpassen
        if submit:
            c.execute(
                """
                UPDATE inventur
                   SET status='submitted',
                       submitted_by=?,
                       submitted_at=?
                 WHERE id=?
                """,
                (username or "", now, inventur_id),
            )
        else:
            c.execute(
                """
                UPDATE inventur
                   SET status='editing'
                 WHERE id=?
                """,
                (inventur_id,),
            )

        cn.commit()


# ---------------------------------------------------------
# Inventur freigeben
# ---------------------------------------------------------
def approve_inventur(inventur_id: int, username: str) -> None:
    _ensure_schema()
    now = datetime.datetime.utcnow().isoformat()
    with conn() as cn:
        c = cn.cursor()
        c.execute(
            """
            UPDATE inventur
               SET status='approved',
                   approved_by=?,
                   approved_at=?
             WHERE id=?
            """,
            (username or "", now, inventur_id),
        )
        cn.commit()


# ---------------------------------------------------------
# Übersicht / Historie
# ---------------------------------------------------------
def list_all_inventuren() -> List[Dict]:
    _ensure_schema()
    with conn() as cn:
        c = cn.cursor()
        rows = c.execute(
            """
            SELECT id, year, month, status,
                   created_by, created_at,
                   submitted_by, submitted_at,
                   approved_by, approved_at
              FROM inventur
             ORDER BY year DESC, month DESC, id DESC
            """
        ).fetchall()

    out: List[Dict] = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "year": r[1],
                "month": r[2],
                "status": r[3],
                "created_by": r[4],
                "created_at": r[5],
                "submitted_by": r[6],
                "submitted_at": r[7],
                "approved_by": r[8],
                "approved_at": r[9],
            }
        )
    return out


def get_inventur_total_value(inventur_id: int) -> float:
    _ensure_schema()
    with conn() as cn:
        c = cn.cursor()
        row = c.execute(
            "SELECT SUM(total_value) FROM inventur_items WHERE inventur_id=?",
            (inventur_id,),
        ).fetchone()
    return float(row[0] or 0.0)
