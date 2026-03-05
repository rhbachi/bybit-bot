import time
import threading
import pandas as pd
from config import *
from flask import Flask, jsonify
from notifier import send_telegram
from strategy import apply_indicators, check_signal
from portfolio import add_position, remove_position, get_positions, lowest_score
from risk_engine import can_open_trade

signals_cache = []

app = Flask(__name__)


@app.route("/api/signals")
def signals():
    return jsonify(signals_cache[-50:])


def start_api():

    print("🌐 API server started on port 5001")

    app.run(host="0.0.0.0", port=5001)


def fetch_data(symbol):

    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)

    df = pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )

    return df


def position_size(price):

    risk = CAPITAL * RISK_PER_TRADE

    position_value = risk * LEVERAGE

    qty = position_value / price

    return round(qty, 6)


# ===============================
# BYBIT PRECISION FIX
# ===============================

def adjust_qty(symbol, qty, price):

    try:

        market = exchange.market(symbol)

        min_amount = market["limits"]["amount"]["min"]
        precision = market["precision"]["amount"]

        qty = round(qty, precision)

        if qty < min_amount:

            send_telegram(
                f"⚠️ Qty too small\n\n{symbol}\nRequired: {min_amount}"
            )

            return None

        min_notional = 5

        if qty * price < min_notional:

            send_telegram(
                f"⚠️ Notional too small\n\n{symbol}"
            )

            return None

        return qty

    except Exception as e:

        send_telegram(f"⚠️ Precision error {symbol}\n{e}")

        return None


def open_trade(symbol, side, price, score):

    def open_trade(symbol, side, price, score):

    qty = position_size(price)

    qty = adjust_qty(symbol, qty, price)

    if qty is None:
        return

    try:

        order = exchange.create_order(
            symbol,
            "market",
            "buy" if side == "long" else "sell",
            qty
        )

        add_position(symbol, {
            "side": side,
            "entry": price,
            "qty": qty,
            "score": score,
            "risk": CAPITAL * RISK_PER_TRADE
        })

        send_telegram(
f"""
📈 TRADE OPEN

Symbol: {symbol}
Side: {side}

Score: {score}

Qty: {qty}
"""
        )

    except Exception as e:

        print(f"Trade error {symbol}: {e}")


def bot_loop():

    send_telegram("🤖 BOT V4.3 STARTED - Trading engine online")

    while True:

        positions = get_positions()

        for symbol in SYMBOLS:

            try:

                print("⏳ Analyse", symbol)

                df = fetch_data(symbol)

                df = apply_indicators(df)

                signal, score = check_signal(df)

                if signal is None:
                    continue

                print(f"🚦 {symbol} {signal} score={score}")

                if score < SCORE_THRESHOLD:
                    continue

                price = df.close.iloc[-1]

                if symbol in positions:
                    continue

                if len(positions) >= MAX_POSITIONS:

                    lowest = lowest_score()

                    if lowest and score > lowest[1]["score"]:

                        remove_position(lowest[0])

                        send_telegram(
                            f"🔄 Replace trade {lowest[0]} with {symbol}"
                        )

                    else:
                        continue

                if not can_open_trade(positions, CAPITAL, RISK_PER_TRADE):
                    continue

                open_trade(symbol, signal, price, score)

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