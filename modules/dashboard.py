# dashboard.py
import streamlit as st
import pandas as pd
import datetime as dt
import plotly.express as px
from db import conn
from ui_theme import page_header, section_title, metric_card


# ----------------------------------------------------------
#  Hilfsfunktionen
# ----------------------------------------------------------

def _table_exists(c, name: str) -> bool:
    row = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _safe_load_daily() -> pd.DataFrame:
    """Lädt Tabelle 'daily' sicher aus der DB, auch wenn sie leer oder fehlerhaft ist."""
    with conn() as cn:
        c = cn.cursor()
        if not _table_exists(c, "daily"):
            return pd.DataFrame()

        try:
            df = pd.read_sql("SELECT * FROM daily ORDER BY date(datum)", cn, parse_dates=["datum"])
        except Exception:
            df = pd.read_sql("SELECT * FROM daily ORDER BY datum", cn)
            if "datum" in df.columns:
                df["datum"] = pd.to_datetime(df["datum"], errors="coerce")

    return df


def _seed_example_rows():
    """Erstellt Beispiel-Daten, falls noch keine Tagesdaten vorhanden sind."""
    today = dt.date.today()
    rows = []
    for i in range(10):
        d = today - dt.timedelta(days=9 - i)
        rows.append((
            d.strftime("%Y-%m-%d"),
            1000 + i * 180,  # umsatz_total
            120+i*5, 130+i*5, 140+i*5, 150+i*5, 160+i*5, 170+i*5, 180+i*5,  # bar1..bar7
            200, 300, 150, 220, 100, 130,  # kassen cash/card
            90  # garderobe_total
        ))

    with conn() as cn:
        c = cn.cursor()
        for r in rows:
            c.execute("""
                INSERT OR REPLACE INTO daily(
                    datum, umsatz_total, bar1,bar2,bar3,bar4,bar5,bar6,bar7,
                    kasse1_cash,kasse1_card,kasse2_cash,kasse2_card,kasse3_cash,kasse3_card,
                    garderobe_total
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, r)
        cn.commit()


# ----------------------------------------------------------
#  Dashboard Rendering
# ----------------------------------------------------------

def render_dashboard():
    page_header("📊 Dashboard", "Dein Überblick über Umsatz, Bars und Kassen")

    df = _safe_load_daily()

    # ----------------------------------------------------------
    #  Kein Datenbestand -> Demo-Erstellung anbieten
    # ----------------------------------------------------------
    if df.empty:
        st.warning("Noch keine Tagesdaten vorhanden. Lege Beispieldaten an oder erfasse Daten in der Abrechnung.")
        if st.button("🔧 Demo-Daten anlegen", use_container_width=True):
            _seed_example_rows()
            st.success("Beispieldaten gespeichert. Öffne das Dashboard erneut.")
        st.stop()

    # ----------------------------------------------------------
    #  Datenbasis aufbereiten
    # ----------------------------------------------------------
    if "datum" in df.columns:
        df = df.sort_values("datum")
        zeitraum = f"{df['datum'].min().date()} → {df['datum'].max().date()}"
    else:
        zeitraum = "Unbekannt"

    st.caption(f"Zeitraum: **{zeitraum}**")
    st.divider()

    # ----------------------------------------------------------
    #  KPIs (Umsatz / Bars / Garderobe)
    # ----------------------------------------------------------
    total = float(df["umsatz_total"].sum()) if "umsatz_total" in df.columns else 0.0
    avg_day = total / len(df) if len(df) > 0 else 0.0
    last_day = float(df["umsatz_total"].iloc[-1]) if "umsatz_total" in df.columns else 0.0

    c1, c2, c3 = st.columns(3)
    metric_card("Gesamtumsatz", f"{total:,.2f} €", "Summe aller Tage")
    metric_card("⌀ Tagesumsatz", f"{avg_day:,.2f} €", "Durchschnitt pro Öffnungstag")
    metric_card("Letzter Tag", f"{last_day:,.2f} €", f"{df['datum'].iloc[-1].strftime('%d.%m.%Y')}")

    st.divider()

    # ----------------------------------------------------------
    #  Zeitreihe Umsatz pro Tag
    # ----------------------------------------------------------
    if "datum" in df.columns and "umsatz_total" in df.columns:
        section_title("Umsatzentwicklung (pro Tag)")
        fig_line = px.line(
            df, x="datum", y="umsatz_total",
            markers=True,
            line_shape="spline",
            color_discrete_sequence=["#00C853"]
        )
        fig_line.update_layout(
            showlegend=False,
            xaxis_title="Datum",
            yaxis_title="Tagesumsatz (€)",
            template="plotly_dark",
            height=350,
            margin=dict(l=30, r=30, t=40, b=30)
        )
        st.plotly_chart(fig_line, use_container_width=True)

    # ----------------------------------------------------------
    #  Aufteilung Bars (Summe)
    # ----------------------------------------------------------
    bar_cols = [c for c in df.columns if c.startswith("bar")]
    if bar_cols:
        section_title("Aufteilung nach Bars (Gesamtumsatz)")
        sums = df[bar_cols].sum(numeric_only=True)
        fig_bar = px.bar(
            x=sums.index,
            y=sums.values,
            text=[f"{v:,.0f}€" for v in sums.values],
            color=sums.values,
            color_continuous_scale="tealgrn"
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_layout(
            xaxis_title="Bar",
            yaxis_title="Umsatz (€)",
            template="plotly_dark",
            height=380
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # ----------------------------------------------------------
    #  Aufteilung Kassen (Summe)
    # ----------------------------------------------------------
    k_cols = [c for c in df.columns if c.startswith("kasse")]
    if k_cols:
        section_title("Kassenumsätze (Cash / Karte)")
        sums_k = df[k_cols].sum(numeric_only=True)
        fig_k = px.bar(
            x=sums_k.index,
            y=sums_k.values,
            text=[f"{v:,.0f}€" for v in sums_k.values],
            color=sums_k.values,
            color_continuous_scale="darkmint"
        )
        fig_k.update_traces(textposition="outside")
        fig_k.update_layout(
            xaxis_title="Kassa",
            yaxis_title="Umsatz (€)",
            template="plotly_dark",
            height=380
        )
        st.plotly_chart(fig_k, use_container_width=True)

    # ----------------------------------------------------------
    #  Letzte 10 Datensätze (Tabelle)
    # ----------------------------------------------------------
    section_title("Letzte Einträge")
    st.dataframe(df.tail(10), use_container_width=True)

    st.caption("© 2025 Roman Petek – Gastro Essentials Beta 1")
