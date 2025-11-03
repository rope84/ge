# inventur.py
import os, io, re
from datetime import datetime, date
from contextlib import closing
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from core.db import conn
from core.ui_theme import page_header, section_title, metric_card
from core.config import APP_NAME, APP_VERSION

EXCEL_PATH = "versuch3.xlsx"
EXPORT_DIR = "exports"
MONTHS = ["Jänner", "Februar", "März", "April", "Mai", "Juni",
          "Juli", "August", "September", "Oktober", "November", "Dezember"]

# ----------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------

def ensure_export_dir():
    os.makedirs(EXPORT_DIR, exist_ok=True)


def items_exist():
    with closing(conn()) as c:
        return c.execute("SELECT COUNT(*) FROM inventur_items").fetchone()[0] > 0


def _norm_colname(s: str) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _coerce_num(x):
    if pd.isna(x):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def import_excel_once_if_empty():
    """Importiert Artikelliste einmalig aus Excel, falls DB leer."""
    if items_exist() or not os.path.exists(EXCEL_PATH):
        return

    df = pd.read_excel(EXCEL_PATH, header=None)
    first_row = df.iloc[0].astype(str).str.lower().tolist()
    looks_like_header = any(k in " ".join(first_row)
                            for k in ["artikel", "ep", "netto", "stand", "kategorie"])
    if looks_like_header:
        df = pd.read_excel(EXCEL_PATH, header=0)

    cols_map = {c: _norm_colname(c) for c in df.columns}
    inv = {}
    for raw, norm in cols_map.items():
        if "kat" in norm:
            inv["kategorie"] = raw
        elif "artikel" in norm or "bezeichnung" in norm:
            inv["artikel"] = raw
        elif "stand" in norm or "bestand" in norm:
            inv["stand"] = raw
        elif "ep netto" in norm or ("ep" in norm and "netto" in norm):
            inv["ep_netto"] = raw

    if "artikel" not in inv:
        inv["artikel"] = df.columns[1]
    if "stand" not in inv:
        for c in df.columns:
            if df[c].astype(str).str.contains(r"\d").any():
                inv["stand"] = c
                break
    if "ep_netto" not in inv:
        inv["ep_netto"] = df.columns[-1]
    if "kategorie" not in inv:
        inv["kategorie"] = None

    use_cols = [inv[k] for k in inv if inv[k] in df.columns and inv[k] is not None]
    df2 = df[use_cols].copy()

    rename_map = {}
    if inv.get("kategorie") in df2.columns:
        rename_map[inv["kategorie"]] = "kategorie"
    rename_map[inv["artikel"]] = "artikel"
    rename_map[inv["stand"]] = "stand"
    rename_map[inv["ep_netto"]] = "ep_netto"
    df2 = df2.rename(columns=rename_map)

    df2["artikel"] = df2["artikel"].astype(str).str.strip()
    df2 = df2[df2["artikel"].str.len() > 0]
    df2["stand"] = df2["stand"].apply(_coerce_num)
    df2["ep_netto"] = df2["ep_netto"].apply(_coerce_num)
    if "kategorie" not in df2.columns:
        df2["kategorie"] = ""

    yy, mm = date.today().year, date.today().month
    now = datetime.now().isoformat()
    rows = [(yy, mm, str(r.get("kategorie", "")), str(r["artikel"]),
             float(r["ep_netto"]), float(r["stand"]), 0.0, "System", now)
            for _, r in df2.iterrows()]

    with closing(conn()) as c:
        c.executemany("""
            INSERT INTO inventur_items
            (jahr,monat,kategorie,artikel,ep_netto,stand_vormonat,stand_aktuell,last_user,last_modified)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, rows)
        c.commit()


def load_inventory(year: int, month: int) -> pd.DataFrame:
    with closing(conn()) as c:
        df = pd.read_sql_query("""
            SELECT * FROM inventur_items
            WHERE jahr=? AND monat=?
            ORDER BY kategorie, artikel
        """, c, params=(year, month))
    return df


def copy_from_previous_or_seed(year: int, month: int):
    with closing(conn()) as c:
        cnt = c.execute("SELECT COUNT(*) FROM inventur_items WHERE jahr=? AND monat=?",
                        (year, month)).fetchone()[0]
        if cnt > 0:
            return

        py, pm = (year, month - 1) if month > 1 else (year - 1, 12)
        prev = pd.read_sql_query("SELECT * FROM inventur_items WHERE jahr=? AND monat=?",
                                 c, params=(py, pm))
        now = datetime.now().isoformat()
        rows = []

        source = prev if not prev.empty else pd.read_sql_query("SELECT * FROM inventur_items", c)
        for _, r in source.iterrows():
            rows.append((year, month, r["kategorie"], r["artikel"], float(r["ep_netto"]),
                         float(r["stand_aktuell"]), 0.0, "System", now))

        if rows:
            c.executemany("""
                INSERT INTO inventur_items
                (jahr,monat,kategorie,artikel,ep_netto,stand_vormonat,stand_aktuell,last_user,last_modified)
                VALUES(?,?,?,?,?,?,?,?,?)
            """, rows)
            c.commit()


def save_inventory(year: int, month: int, df: pd.DataFrame, user: str):
    now = datetime.now().isoformat()
    with closing(conn()) as c:
        c.execute("DELETE FROM inventur_items WHERE jahr=? AND monat=?", (year, month))
        rows = []
        for _, r in df.iterrows():
            rows.append((year, month, str(r["kategorie"]), str(r["artikel"]),
                         float(r["ep_netto"]), float(r["stand_vormonat"]),
                         float(r["stand_aktuell"]), user, now))
        c.executemany("""
            INSERT INTO inventur_items
            (jahr,monat,kategorie,artikel,ep_netto,stand_vormonat,stand_aktuell,last_user,last_modified)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, rows)
        c.execute("""
            INSERT INTO inventur_logs(jahr,monat,artikel,user,changed_at,note)
            VALUES(?,?,?,?,?,?)
        """, (year, month, "*", user, now, "Inventur gespeichert"))
        c.commit()


def is_locked(year: int, month: int) -> bool:
    with closing(conn()) as c:
        changed = c.execute("SELECT COUNT(*) FROM inventur_logs WHERE jahr=? AND monat=?",
                            (year, month)).fetchone()[0]
    return changed > 0


def make_inventory_pdf(year: int, month: int, df: pd.DataFrame):
    ensure_export_dir()
    fname = os.path.join(EXPORT_DIR, f"Inventur_{year}_{month:02d}.pdf")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 40

    def line(txt, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if not bold else 12)
        c.drawString(40, y, str(txt))
        y -= 16
        if y < 60:
            c.showPage()
            y = h - 40

    line(f"Gastro Essentials – Inventur {year}-{month:02d}", bold=True)
    line(f"Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    line("")
    total = 0.0
    cur_cat = None
    for _, r in df.sort_values(["kategorie", "artikel"]).iterrows():
        if r["kategorie"] != cur_cat:
            cur_cat = r["kategorie"]
            line(f"[{cur_cat}]", bold=True)
        wert = float(r["stand_aktuell"]) * float(r["ep_netto"])
        total += wert
        line(f"{r['artikel']} | EP: {r['ep_netto']:.2f} | Vormonat: {r['stand_vormonat']:.2f} | "
             f"Aktuell: {r['stand_aktuell']:.2f} | Gesamt: {wert:.2f} €")
    line("")
    line(f"Summe Netto: {total:.2f} €", bold=True)
    line("")
    line("Kontrolliert: __________________________  Datum: _______________")
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 20, "© Roman Petek. Alle Rechte vorbehalten.")
    c.save()

    with open(fname, "wb") as f:
        f.write(buf.getvalue())
    return fname


# ----------------------------------------------------------
# Haupt-Render-Funktion
# ----------------------------------------------------------

def render_inventur(role: str, username: str):
    page_header("📦 Inventur", "Artikelbestände prüfen und dokumentieren")

    yy_list = list(range(2023, date.today().year + 1))
    year = st.selectbox("Jahr", yy_list, index=yy_list.index(date.today().year))

    section_title("Monat wählen")
    mcols = st.columns(12)
    sel_month = st.session_state.get("__inv_month", date.today().month)
    for i, mc in enumerate(mcols, start=1):
        if mc.button(MONTHS[i - 1], key=f"m_{year}_{i}", use_container_width=True):
            sel_month = i
            st.session_state.__inv_month = i

    st.divider()
    copy_from_previous_or_seed(year, sel_month)
    df = load_inventory(year, sel_month)

    if df.empty:
        st.info("Keine Daten für diese Periode.")
        return

    df["gesamt_netto"] = df["ep_netto"].fillna(0) * df["stand_aktuell"].fillna(0)
    locked = is_locked(year, sel_month)
    readonly = (role != "admin" and locked)

    st.caption("Nach dem ersten Speichern ist die Periode für Nicht-Admins gesperrt.")
    section_title(f"Inventur {MONTHS[sel_month-1]} {year}")

    ed = st.data_editor(
        df[["id", "kategorie", "artikel", "ep_netto", "stand_vormonat", "stand_aktuell",
            "gesamt_netto", "last_user", "last_modified"]],
        hide_index=True, use_container_width=True,
        disabled=["gesamt_netto", "last_user", "last_modified"]
        if not readonly else df.columns.tolist(),
        column_config={
            "ep_netto": st.column_config.NumberColumn("EP Netto (€)", format="%.2f"),
            "stand_vormonat": st.column_config.NumberColumn("Stand Vormonat", format="%.2f"),
            "stand_aktuell": st.column_config.NumberColumn("Stand Aktuell", format="%.2f"),
            "gesamt_netto": st.column_config.NumberColumn("Gesamt Netto (€)", format="%.2f"),
        },
        key=f"inv_{year}_{sel_month}"
    )

    st.divider()
    c1, c2, c3 = st.columns(3)

    if c1.button("🆕 Neue Inventur starten", use_container_width=True):
        copy_from_previous_or_seed(date.today().year, date.today().month)
        st.success("Neue Inventurperiode vorbereitet.")
        st.rerun()

    if readonly:
        c2.info("Diese Periode ist gesperrt – nur Admin kann ändern.")
    else:
        if c2.button("💾 Speichern", use_container_width=True):
            save_inventory(year, sel_month, ed, username or "User")
            st.success("Inventur gespeichert.")
            st.rerun()

    if c3.button("📄 PDF erstellen", use_container_width=True):
        fresh = load_inventory(year, sel_month)
        fname = make_inventory_pdf(year, sel_month, fresh)
        with open(fname, "rb") as f:
            st.download_button("PDF herunterladen", f.read(),
                               file_name=os.path.basename(fname),
                               mime="application/pdf",
                               key=f"pdf_{year}_{sel_month}")
