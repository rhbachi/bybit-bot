import time
import threading
import pandas as pd

from flask import Flask, jsonify

from config import *
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
        columns=["time","open","high","low","close","volume"]
    )

    return df


def position_size(price):

    risk = CAPITAL * RISK_PER_TRADE

    position_value = risk * LEVERAGE

    qty = position_value / price

    return round(qty, 4)


def open_trade(symbol, side, price, score):

    qty = position_size(price)

    if qty <= 0:
        return

    try:

        order = exchange.create_order(
            symbol,
            "market",
            "buy" if side == "long" else "sell",
            qty
        )

        add_position(symbol,{
            "side":side,
            "entry":price,
            "qty":qty,
            "score":score,
            "risk":CAPITAL*RISK_PER_TRADE
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

        send_telegram(f"❌ Trade error {symbol}\n{e}")


def bot_loop():

    send_telegram("🤖 BOT V4.3 STARTED")

    while True:

        positions = get_positions()

        for symbol in SYMBOLS:

            print("⏳ Analyse",symbol)

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
                "symbol":symbol,
                "signal":signal,
                "score":score
            })

        time.sleep(30)


if __name__ == "__main__":

    t = threading.Thread(target=start_api)

    t.daemon = True
    t.start()

    bot_loop()