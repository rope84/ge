# start.py
import streamlit as st
import datetime
import random
from core.ui_theme import page_header, section_title, metric_card
from core.config import APP_NAME, APP_VERSION

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

    # Lustiger Spruch / Zitat
    st.markdown(
    f"<p style='text-align:center; font-size:17px; font-style:italic; opacity:0.8;'>💬 {get_daily_quote()}</p>",
    unsafe_allow_html=True
)

    st.divider()

    # Aktionen
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💰 Abrechnung öffnen", use_container_width=True):
            st.session_state["nav_choice"] = "Abrechnung"
            st.rerun()

    with col2:
        if st.button("📦 Inventur starten", use_container_width=True):
            st.session_state["nav_choice"] = "Inventur"
            st.rerun()

    with col3:
        if st.button("📊 Dashboard ansehen", use_container_width=True):
            st.session_state["nav_choice"] = "Dashboard"
            st.rerun()

    st.divider()

    # Optionaler Footer mit kleinerem Text
    st.caption(
        f"© 2025 Roman Petek – {APP_NAME} {APP_VERSION}"
    )
