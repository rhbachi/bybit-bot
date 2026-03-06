import time
import threading
import pandas as pd
import math

from config import *
from flask import Flask, jsonify
from notifier import send_telegram
from strategy_v6 import apply_indicators, check_signal

signals_cache = []

app = Flask(__name__)


@app.route("/api/signals")
def signals():
    return jsonify(signals_cache[-50:])


def start_api():
    print("🌐 API server started on port 5001")
    app.run(host="0.0.0.0", port=5001)


# ================================
# FETCH MARKET DATA
# ================================

def fetch_data(symbol):

    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)

    df = pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )

    return df


# ================================
# ATR POSITION SIZE
# ================================

def position_size(price, atr):

    risk = CAPITAL * RISK_PER_TRADE

    stop_distance = atr * SL_ATR_MULTIPLIER

    if stop_distance == 0:
        return None

    qty = risk / stop_distance

    qty = qty * LEVERAGE

    # cap position size (safety)
    max_position_value = CAPITAL * LEVERAGE * 0.25
    max_qty = max_position_value / price

    if qty > max_qty:
        qty = max_qty

    return qty


# ================================
# BYBIT PRECISION ENGINE
# ================================

def adjust_qty(symbol, qty, price):

    try:

        market = exchange.market(symbol)

        min_amount = market["limits"]["amount"]["min"]
        precision = market["precision"]["amount"]

        if isinstance(precision, float):
            precision = abs(int(round(-math.log10(precision))))

        qty = round(qty, precision)

        if qty < min_amount:
            return None

        # minimum notional
        if qty * price < 5:
            return None

        return qty

    except Exception as e:

        send_telegram(f"⚠️ Precision error {symbol}\n{e}")
        return None


# ================================
# OPEN TRADE
# ================================

def open_trade(symbol, side, price, atr, score):

    qty = position_size(price, atr)

    if qty is None:
        return

    qty = adjust_qty(symbol, qty, price)

    if qty is None:
        return

    try:

        exchange.create_order(
            symbol,
            "market",
            "buy" if side == "long" else "sell",
            qty
        )

        send_telegram(
f"""
📈 TRADE OPEN V6

Symbol: {symbol}
Side: {side}

Score: {score}
ATR: {round(atr,4)}

Qty: {qty}
"""
        )

    except Exception as e:

        send_telegram(f"❌ Trade error {symbol}\n{e}")


# ================================
# BOT LOOP
# ================================

def bot_loop():

    send_telegram("🚀 BOT V6 STARTED")

    while True:

        for symbol in SYMBOLS:

            try:

                print("⏳ Analyse", symbol)

                df = fetch_data(symbol)

                df = apply_indicators(df)

                signal, score, atr = check_signal(df)

                if signal is None:
                    continue

                if score < SCORE_THRESHOLD:
                    continue

                price = df.close.iloc[-1]

                open_trade(symbol, signal, price, atr, score)

                signals_cache.append({
                    "symbol": symbol,
                    "signal": signal,
                    "score": score
                })

            except Exception as e:

                print("Bot error:", e)

        time.sleep(120)


if __name__ == "__main__":

    t = threading.Thread(target=start_api)

    t.daemon = True
    t.start()

    bot_loop()