import os
import time
import sqlite3
import requests
import pandas as pd
from threading import Thread
from flask import Flask, jsonify

from config import (
    exchange,
    SYMBOLS,
    TIMEFRAME,
    CAPITAL,
    RISK_PER_TRADE,
    LEVERAGE,
    SCORE_THRESHOLD,
    MAX_POSITIONS,
    COOLDOWN_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID
)

from strategy import apply_indicators, check_signal


# ================= TELEGRAM =================

def send_telegram(msg):

    if TELEGRAM_BOT_TOKEN == "" or TELEGRAM_CHAT_ID == "":
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass


# ================= DATABASE =================

os.makedirs("data", exist_ok=True)

conn = sqlite3.connect("data/trades.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trades (
id INTEGER PRIMARY KEY AUTOINCREMENT,
symbol TEXT,
side TEXT,
entry REAL,
qty REAL,
timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()


# ================= API DASHBOARD =================

app = Flask(__name__)
signals_cache = []

@app.route("/api/signals")
def get_signals():
    return jsonify(signals_cache)


def start_api():

    print("🌐 API server started on port 5001", flush=True)

    app.run(host="0.0.0.0", port=5001)


# ================= COOLDOWN =================

last_trade_time = {}


# ================= CORRELATION GROUPS =================

CORRELATION_GROUPS = {

    "majors": [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT"
    ],

    "alts": [
        "SOL/USDT:USDT",
        "BNB/USDT:USDT",
        "ADA/USDT:USDT",
        "DOT/USDT:USDT"
    ]
}


# ================= OPEN POSITIONS =================

def get_open_positions():

    try:

        positions = exchange.fetch_positions()

        open_symbols = []

        for p in positions:

            contracts = float(p.get("contracts", 0) or 0)

            if contracts > 0:
                open_symbols.append(p["symbol"])

        return open_symbols

    except Exception as e:

        print("⚠️ fetch_positions error:", e)

        return []


def correlated_position_exists(symbol, open_positions):

    for group in CORRELATION_GROUPS.values():

        if symbol in group:

            for s in group:

                if s in open_positions:
                    return True

    return False


# ================= POSITION SIZE =================

def size_from_score(score):

    if score >= 5:
        return 1.5

    if score == 4:
        return 1.2

    if score == 3:
        return 1.0

    if score == 2:
        return 0.7

    return 0


def calculate_position_size(symbol, price, score):

    multiplier = size_from_score(score)

    position_value = CAPITAL * RISK_PER_TRADE * LEVERAGE * multiplier

    qty = position_value / price

    min_qty = 0.001

    if "ETH" in symbol:
        min_qty = 0.01

    if "XRP" in symbol:
        min_qty = 1

    qty = max(qty, min_qty)

    return round(qty, 4)


# ================= DATA =================

def fetch_ohlcv(symbol):

    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)

    df = pd.DataFrame(
        ohlcv,
        columns=["time","open","high","low","close","volume"]
    )

    return df


# ================= TRADE =================

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

    qty = float(qty)

    print(f"📦 Order params | {symbol} | {order_side} | qty={qty}")

    exchange.create_order(
        symbol=symbol,
        type="market",
        side=order_side,
        amount=qty,
        params={
            "stopLoss": round(sl, 4),
            "takeProfit": round(tp, 4),
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice"
        }
    )

    print(
        f"📈 TRADE | {symbol} | {side.upper()} | Qty={qty}",
        flush=True
    )

    send_telegram(
        f"""
🚨 TRADE OUVERT

Symbol: {symbol}
Side: {side.upper()}
Entry: {round(price,4)}

SL: {round(sl,4)}
TP: {round(tp,4)}

Qty: {qty}
"""
    )

    cursor.execute(
        "INSERT INTO trades(symbol,side,entry,qty) VALUES(?,?,?,?)",
        (symbol, side, price, qty)
    )

    conn.commit()

    last_trade_time[symbol] = time.time()


# ================= BOT LOOP =================

def run_bot():

    global signals_cache

    print("🤖 MultiSymbol Bot V3.1 démarré", flush=True)

    send_telegram("🤖 MultiSymbol Bot démarré")

    while True:

        try:

            open_positions = get_open_positions()

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

                print(f"🚦 Signal {symbol} = {signal} | Score={score}")

                if score < SCORE_THRESHOLD:
                    print("⚠️ Signal rejeté")
                    continue

                if len(open_positions) >= MAX_POSITIONS:
                    print("⚠️ Max positions atteint")
                    continue

                if correlated_position_exists(symbol, open_positions):
                    print("⚠️ Position corrélée détectée")
                    continue

                if symbol in last_trade_time:

                    if time.time() - last_trade_time[symbol] < COOLDOWN_SECONDS:
                        print("⏳ Cooldown actif")
                        continue

                price = df.iloc[-1].close

                qty = calculate_position_size(symbol, price, score)

                open_trade(symbol, signal, price, qty)

            time.sleep(30)

        except Exception as e:

            print("❌ Erreur MultiSymbol:", e)

            send_telegram(f"❌ Bot error: {e}")

            time.sleep(30)


# ================= START =================

Thread(target=start_api, daemon=True).start()

run_bot()