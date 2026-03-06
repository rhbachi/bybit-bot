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
# FETCH DATA
# ================================

def fetch_data(symbol):

    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)

    df = pd.DataFrame(
        ohlcv,
        columns=["time","open","high","low","close","volume"]
    )

    return df


# ================================
# ATR POSITION SIZING
# ================================

def position_size(price, atr):

    risk = CAPITAL * RISK_PER_TRADE

    stop_distance = atr * SL_ATR_MULTIPLIER

    if stop_distance == 0:
        return None

    qty = risk / stop_distance

    qty = qty * LEVERAGE

    # limite max position (protection)
    max_position_value = CAPITAL * LEVERAGE * 0.2
    max_qty = max_position_value / price

    if qty > max_qty:
        qty = max_qty

    return qty


# ================================
# PRECISION ENGINE
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

        # check notional
        if qty * price < 5:
            return None

        return qty

    except Exception as e:

        send_telegram(f"⚠️ Precision error {symbol}\n{e}")
        return None


# ================================
# MARGIN CHECK
# ================================

def margin_available(price, qty):

    try:

        balance = exchange.fetch_balance()

        # récupération correcte pour Bybit futures
        available = balance.get("free", {}).get("USDT", 0)

        if available is None:
            available = 0

        required_margin = (qty * price) / LEVERAGE

        if required_margin > available:

            send_telegram(
f"""⚠️ Not enough margin

Required: {round(required_margin,2)}
Available: {round(available,2)}
"""
            )

            return False

        return True

    except Exception as e:

        send_telegram(f"⚠️ Balance check error\n{e}")
        return False


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

    if not margin_available(price, qty):
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
📈 TRADE OPEN V6.1

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

    send_telegram("🚀 BOT V6.1 STARTED")

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