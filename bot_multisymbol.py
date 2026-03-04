import time
import os
import sqlite3
import pandas as pd
from flask import Flask, jsonify
from threading import Thread

from config import (
    exchange,
    SYMBOLS,
    TIMEFRAME,
    CAPITAL,
    RISK_PER_TRADE,
    LEVERAGE,
    SCORE_THRESHOLD
)

from strategy import apply_indicators, check_signal


# =========================
# CREATE DATA FOLDER
# =========================

os.makedirs("data", exist_ok=True)

# =========================
# DATABASE
# =========================

conn = sqlite3.connect("data/trades.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
id INTEGER PRIMARY KEY AUTOINCREMENT,
symbol TEXT,
side TEXT,
entry REAL,
exit REAL,
qty REAL,
pnl REAL,
result TEXT,
timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()


# =========================
# API FOR DASHBOARD
# =========================

app = Flask(__name__)
signals_cache = []


@app.route("/api/signals")
def api_signals():
    return jsonify(signals_cache)


def start_api():
    print("🌐 API server started on port 5001", flush=True)
    app.run(host="0.0.0.0", port=5001)


# =========================
# POSITION SIZE
# =========================

def calculate_position_size(price):

    risk_amount = CAPITAL * RISK_PER_TRADE

    position_value = risk_amount * LEVERAGE

    qty = position_value / price

    return round(qty, 4)


# =========================
# FETCH MARKET DATA
# =========================

def fetch_ohlcv(symbol):

    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)

    df = pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )

    return df


# =========================
# TRADE EXECUTION
# =========================

def open_trade(symbol, side, price, qty):

    RR = 2.3
    SL_PCT = 0.006

    if side == "long":

        sl = price * (1 - SL_PCT)
        tp = price + (price - sl) * RR
        order_side = "buy"

    else:

        sl = price * (1 + SL_PCT)
        tp = price - (sl - price) * RR
        order_side = "sell"

    exchange.create_market_order(
        symbol,
        order_side,
        qty,
        params={
            "stopLoss": sl,
            "takeProfit": tp,
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice"
        }
    )

    print(
        f"📈 TRADE | {symbol} | {side.upper()} | SL={round(sl,2)} | TP={round(tp,2)} | Qty={qty}",
        flush=True
    )


# =========================
# MAIN BOT LOOP
# =========================

def run_bot():

    global signals_cache

    print("🤖 MultiSymbol Bot PRO démarré", flush=True)

    while True:

        try:

            for symbol in SYMBOLS:

                print(f"⏳ Analyse {symbol}", flush=True)

                df = fetch_ohlcv(symbol)

                df = apply_indicators(df)

                signal, score = check_signal(df)

                signals_cache.append({
                    "symbol": symbol,
                    "signal": signal,
                    "score": score
                })

                if len(signals_cache) > 50:
                    signals_cache = signals_cache[-50:]

                if signal is None:
                    continue

                print(f"🚦 Signal {symbol} = {signal} | Score={score}", flush=True)

                if score < SCORE_THRESHOLD:
                    print(f"⚠️ Signal rejeté | Score={score}", flush=True)
                    continue

                price = df.iloc[-1].close

                qty = calculate_position_size(price)

                open_trade(symbol, signal, price, qty)

            time.sleep(60)

        except Exception as e:

            print("❌ Erreur MultiSymbol:", e, flush=True)

            time.sleep(30)


# =========================
# START THREADS
# =========================

Thread(target=start_api, daemon=True).start()

run_bot()