# start.py
import streamlit as st
import datetime
import random
from ui_theme import page_header, section_title, metric_card

# --- Tages-Sprüche / Zitate ---
QUOTES = [
    "Manchmal ist der beste Drink der, den man nicht verschüttet. 🍸",
    "Ein voller Club ist gut – ein voller Kühlschrank ist besser. 😎",
    "Erfolg ist, wenn der letzte Gast geht und du trotzdem noch lächelst.",
    "Heute ist der perfekte Tag für gute Musik und starke Umsätze!",
    "Hinter jeder Bar steht ein Held – oder zumindest jemand, der so aussieht. 🍹",
    "Wer den Überblick behält, braucht keinen Kater. 😉",
    "Ein bisschen Chaos gehört zum Clubleben – aber nicht in den Zahlen. 💼",
    "Mehr Umsatz, weniger Sorgen. Das ist Gastro Essentials. 💡",
    "Gute Stimmung kann man nicht kaufen – aber sie zahlt sich aus. 🎶",
    "Wenn du lächelst, läuft’s. 😄"
]

def get_daily_quote():
    """Gibt für jeden Tag einen fixen zufälligen Spruch zurück."""
    today = datetime.date.today()
    random.seed(today.toordinal())
    return random.choice(QUOTES)


# --- Render Funktion ---
def render_start(username: str):
    # Header im zentralen Design
    page_header("Willkommen", f"Hi {username}, was möchtest du heute machen?")
    section_title("Schnellauswahl")

    # Lustiger Spruch / Zitat
    st.markdown(
        f"<p style='font-size:18px; font-style:italic; color:gray;'>💬 {get_daily_quote()}</p>",
        unsafe_allow_html=True
    )

    st.divider()

    # Aktionen
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💰 Abrechnung öffnen", use_container_width=True):
            st.session_state["page"] = "Abrechnung"
            st.success("Wechsle zur Abrechnung …")
            st.rerun()

    with col2:
        if st.button("📦 Inventur starten", use_container_width=True):
            st.session_state["page"] = "Inventur"
            st.info("Inventur wird geladen …")
            st.rerun()

    with col3:
        if st.button("📊 Dashboard ansehen", use_container_width=True):
            st.session_state["page"] = "Dashboard"
            st.info("Dashboard wird geöffnet …")
            st.rerun()

    st.divider()

    # Optionaler Footer mit kleinerem Text
    st.caption(
        "💡 Tipp: Du kannst jederzeit links im Menü zwischen den Modulen wechseln.\n"
        "© 2025 Roman Petek | Gastro Essentials Beta 1"
    )
