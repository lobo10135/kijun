import datetime
import io
import os
import urllib.request
from fpdf import FPDF
import pandas as pd
import streamlit as st
import yfinance as yf

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Kijun-Sen 4H Scanner + SL & TP", layout="wide")


@st.cache_data(ttl=86400)
def get_sp500_tickers():
    """Holt die aktuelle Liste aller S&P 500 Ticker via Wikipedia mit Custom User-Agent.

    Inklusive Fallback via GitHub Open Data bei Verbindungsfehlern.
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
            )
        },
    )

    try:
        with urllib.request.urlopen(req) as response:
            html_content = response.read().decode("utf-8")

        tables = pd.read_html(io.StringIO(html_content))
        df = tables[0]
        tickers = df["Symbol"].tolist()
        return [t.replace(".", "-") for t in tickers]

    except Exception as e:
        st.warning(
            f"Wikipedia-Abruf nicht möglich ({e}). Lade Fallback-Liste von"
            " GitHub..."
        )
        try:
            fallback_url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
            df_fallback = pd.read_csv(fallback_url)
            tickers = df_fallback["Symbol"].tolist()
            return [t.replace(".", "-") for t in tickers]
        except Exception as e_fallback:
            st.error(f"Fallback-Abruf ebenfalls fehlgeschlagen: {e_fallback}")
            return []


def calculate_kijun_sen(data, period=26):
    """Berechnet die Kijun-Sen (Basislinie) = (26-High + 26-Low) / 2."""
    high_26 = data["High"].rolling(window=period).max()
    low_26 = data["Low"].rolling(window=period).min()
    return (high_26 + low_26) / 2


def generate_pdf_report(df_long, df_short):
    """Erstellt einen erweiterten PDF-Bericht inkl. Stop Loss und Take Profit."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")  # Querformat
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(
        0, 10, "Kijun-Sen 4H Signal Report (mit SL & TP)", ln=True, align="C"
    )
    pdf.set_font("Arial", "", 10)
    pdf.cell(
        0,
        8,
        f"Erstellt am: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ln=True,
        align="C",
    )
    pdf.ln(5)

    def print_table(title, df_signals):
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, f"{title} ({len(df_signals)})", ln=True)
        pdf.set_font("Arial", "B", 8)

        cols = [22, 28, 28, 28, 28, 28, 28, 32]
        headers = [
            "Ticker",
            "Schlusskurs",
            "Kijun-Sen",
            "Stop Loss",
            "Take Profit",
            "Risiko ($)",
            "Risiko (%)",
            "Zeitpunkt",
        ]

        for i, h in enumerate(headers):
            pdf.cell(cols[i], 6, h, 1)
        pdf.ln()

        pdf.set_font("Arial", "", 8)
        if df_signals.empty:
            pdf.cell(sum(cols), 6, "Keine Signale vorhanden", 1)
            pdf.ln()
        else:
            for _, row in df_signals.iterrows():
                pdf.cell(cols[0], 6, str(row["Ticker"]), 1)
                pdf.cell(cols[1], 6, f"{row['Close']:.2f}", 1)
                pdf.cell(cols[2], 6, f"{row['Kijun_Sen']:.2f}", 1)
                pdf.cell(cols[3], 6, f"{row['Stop_Loss']:.2f}", 1)
                pdf.cell(cols[4], 6, f"{row['Take_Profit']:.2f}", 1)
                pdf.cell(cols[5], 6, f"{row['Risiko_Absolut']:.2f}", 1)
                pdf.cell(cols[6], 6, f"{row['Risiko_%']:.2f}%", 1)
                pdf.cell(cols[7], 6, str(row["Zeitpunkt (UTC)"]), 1)
                pdf.ln()
        pdf.ln(5)

    print_table("Long Signale (Kijun-Sen nach oben gekreuzt)", df_long)
    print_table("Short Signale (Kijun-Sen nach unten gekreuzt)", df_short)

    return pdf.output(dest="S").encode("latin-1", errors="replace")


# --- MAIN INTERFACE (Zentriert mit bulle.jpg) ---
_, col_center, _ = st.columns([1, 2, 1])

with col_center:
    if os.path.exists("bulle.jpg"):
        st.image("bulle.jpg", use_container_width=True)

    st.markdown("### 📈 Kijun-Sen (Basislinie) 4H Scanner + SL & TP")
    st.markdown(
        "Überprüft ausgewählte Märkte auf Crossover-Signale der **Kijun-Sen** im **4-Stunden-Chart** "
        "auf der letzten abgeschlossenen Kerze und berechnet **Stop Loss** sowie **Take Profit**."
    )

st.sidebar.header("Einstellungen")
kijun_period = st.sidebar.number_input(
    "Kijun-Sen Periode", min_value=10, max_value=50, value=26
)
swing_lookback = st.sidebar.number_input(
    "Lookback für Hoch/Tief (Kerzen)",
    min_value=3,
    max_value=30,
    value=10,
    help="Anzahl der letzten 4H-Kerzen zur Ermittlung des Bewegungs-Extrems.",
)
tp_factor = (
    st.sidebar.slider(
        "Take Profit Faktor (%)",
        min_value=1.0,
        max_value=50.0,
        value=10.0,
        step=1.0,
        help="Prozentsatz der Strecke zwischen Hoch/Tief und Einstieg für den TP.",
    )
    / 100.0
)

limit_tickers = st.sidebar.checkbox(
    "Testmodus (nur erste 30 Ticker scannen bei S&P500)", value=False
)

st.markdown("---")
st.markdown("### 🚀 Markt auswählen und Scan starten")

col1, col2, col3, col4 = st.columns(4)
with col1:
    btn_sp500 = st.button("S&P 500 Scan", type="primary", use_container_width=True)
with col2:
    btn_forex = st.button("💱 Währungspaare", use_container_width=True)
with col3:
    btn_indices = st.button("📊 Indizes", use_container_width=True)
with col4:
    btn_metals = st.button("🪙 Edelmetalle", use_container_width=True)

st.markdown("---")

# Bestimmen, welcher Button geklickt wurde und welche Ticker geladen werden sollen
tickers = []
scan_triggered = False

if btn_sp500:
    tickers = get_sp500_tickers()
    if limit_tickers:
        tickers = tickers[:30]
        st.warning("⚠️ Testmodus aktiv: Es werden nur 30 Ticker gescannt.")
    scan_triggered = True

elif btn_forex:
    tickers = [
        "EURUSD=X",
        "GBPUSD=X",
        "USDJPY=X",
        "AUDUSD=X",
        "USDCAD=X",
        "NZDUSD=X",
        "USDCHF=X",
        "EURGBP=X",
        "EURJPY=X",
        "GBPJPY=X",
    ]
    scan_triggered = True

elif btn_indices:
    tickers = [
        "^GSPC",
        "^DJI",
        "^IXIC",
        "^RUT",
        "^FTSE",
        "^GDAXI",
        "^FCHI",
        "^N225",
        "^STOXX50E",
    ]
    scan_triggered = True

elif btn_metals:
    tickers = ["GC=F", "SI=F", "PL=F", "PA=F", "GLD", "SLV"]
    scan_triggered = True

if scan_triggered:
    if not tickers:
        st.error(
            "Keine Ticker vorhanden. Bitte Internetverbindung oder Datenquelle"
            " prüfen."
        )
        st.stop()

    st.info(
        f"Lade 4H-Daten für {len(tickers)} Ticker herunter. Dies kann einen"
        " Moment dauern..."
    )

    long_signals = []
    short_signals = []

    progress_bar = st.progress(0)

    try:
        data = yf.download(
            tickers, period="60d", interval="1h", group_by="ticker", progress=False
        )
    except Exception as e:
        st.error(f"Fehler beim Datenabruf via yfinance: {e}")
        st.stop()

    for idx, ticker in enumerate(tickers):
        progress_bar.progress((idx + 1) / len(tickers))

        try:
            if len(tickers) == 1:
                df = data.copy()
            else:
                if ticker not in data.columns.levels[0]:
                    continue
                df = data[ticker].dropna(how="all")

            if df.empty or len(df) < (kijun_period * 4):
                continue

            # Resample auf 4H
            df_4h = (
                df.resample("4h")
                .agg(
                    {
                        "Open": "first",
                        "High": "max",
                        "Low": "min",
                        "Close": "last",
                        "Volume": "sum",
                    }
                )
                .dropna()
            )

            if len(df_4h) < (kijun_period + swing_lookback + 2):
                continue

            # Kijun-Sen berechnen
            df_4h["Kijun_Sen"] = calculate_kijun_sen(df_4h, period=kijun_period)

            # Crossover-Check auf zuletzt abgeschlossener Kerze (-2)
            prev_close = df_4h["Close"].iloc[-3]
            prev_kijun = df_4h["Kijun_Sen"].iloc[-3]

            curr_close = df_4h["Close"].iloc[-2]
            curr_kijun = df_4h["Kijun_Sen"].iloc[-2]

            if pd.isna(prev_kijun) or pd.isna(curr_kijun):
                continue

            # Ausschnitt der letzten Kerzen für das Bewegungs-Hoch/Tief
            recent_candles = df_4h.iloc[-(swing_lookback + 2) : -1]

            # LONG: Kijun von unten nach oben gekreuzt
            if prev_close <= prev_kijun and curr_close > curr_kijun:
                stop_loss = recent_candles["Low"].min()
                move_dist = curr_close - stop_loss  # Distanz Tief bis Einstieg
                take_profit = curr_close + (tp_factor * move_dist)

                risiko_abs = curr_close - stop_loss
                risiko_pct = (
                    (risiko_abs / curr_close) * 100 if curr_close > 0 else 0
                )

                long_signals.append(
                    {
                        "Ticker": ticker,
                        "Close": round(curr_close, 2),
                        "Kijun_Sen": round(curr_kijun, 2),
                        "Stop_Loss": round(stop_loss, 2),
                        "Take_Profit": round(take_profit, 2),
                        "Risiko_Absolut": round(risiko_abs, 2),
                        "Risiko_%": round(risiko_pct, 2),
                        "Zeitpunkt (UTC)": df_4h.index[-2].strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                    }
                )

            # SHORT: Kijun von oben nach unten gekreuzt
            elif prev_close >= prev_kijun and curr_close < curr_kijun:
                stop_loss = recent_candles["High"].max()
                move_dist = stop_loss - curr_close  # Distanz Hoch bis Einstieg
                take_profit = curr_close - (tp_factor * move_dist)

                risiko_abs = stop_loss - curr_close
                risiko_pct = (
                    (risiko_abs / curr_close) * 100 if curr_close > 0 else 0
                )

                short_signals.append(
                    {
                        "Ticker": ticker,
                        "Close": round(curr_close, 2),
                        "Kijun_Sen": round(curr_kijun, 2),
                        "Stop_Loss": round(stop_loss, 2),
                        "Take_Profit": round(take_profit, 2),
                        "Risiko_Absolut": round(risiko_abs, 2),
                        "Risiko_%": round(risiko_pct, 2),
                        "Zeitpunkt (UTC)": df_4h.index[-2].strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                    }
                )

        except Exception:
            continue

    progress_bar.empty()
    st.success("Scan abgeschlossen!")

    # --- RESULTS DISPLAY ---
    df_long = pd.DataFrame(long_signals)
    df_short = pd.DataFrame(short_signals)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"🟢 Long Signale ({len(df_long)})")
        if not df_long.empty:
            st.dataframe(df_long, use_container_width=True)
        else:
            st.info("Keine Long-Signale auf der letzten 4H-Kerze gefunden.")

    with col2:
        st.subheader(f"🔴 Short Signale ({len(df_short)})")
        if not df_short.empty:
            st.dataframe(df_short, use_container_width=True)
        else:
            st.info("Keine Short-Signale auf der letzten 4H-Kerze gefunden.")

    # --- PDF EXPORT ---
    if not df_long.empty or not df_short.empty:
        st.markdown("---")
        pdf_bytes = generate_pdf_report(df_long, df_short)
        st.download_button(
            label="📄 Ergebnisse als PDF exportieren",
            data=pdf_bytes,
            file_name=(
                "Kijun_4H_Signals_TP_SL_"
                f"{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            ),
            mime="application/pdf",
        )
