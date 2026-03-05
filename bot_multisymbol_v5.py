import time
import threading
import pandas as pd
from flask import Flask, jsonify

from config import *
from strategy import apply_indicators, check_signal
from precision import adjust_quantity
from notifier import send_telegram

app = Flask(__name__)

signals_log = []


@app.route("/api/signals")
def api_signals():
    return jsonify(signals_log[-50:])


def fetch_ohlcv(symbol):

    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)

    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    return df


def calculate_position_size(price):

    capital_risk = CAPITAL * RISK_PER_TRADE

    position_value = capital_risk * LEVERAGE

    qty = position_value / price

    return qty


def place_trade(symbol, side, price, atr, score):

    try:

        qty = calculate_position_size(price)

        qty = adjust_quantity(exchange, symbol, qty, price)

        if qty is None:
            print(f"⚠️ Qty trop petite {symbol}")
            return

        if PAPER_TRADING:
            print(f"PAPER TRADE {symbol} {side} {qty}")
            return

        order = exchange.create_market_order(symbol, side, qty)

        sl = None
        tp = None

        if side == "buy":

            sl = price - atr * SL_ATR_MULTIPLIER
            tp = price + atr * TP_ATR_MULTIPLIER

        else:

            sl = price + atr * SL_ATR_MULTIPLIER
            tp = price - atr * TP_ATR_MULTIPLIER

        msg = f"""
📈 TRADE OPEN

Symbol: {symbol}
Side: {side}

Entry: {price}
SL: {round(sl,4)}
TP: {round(tp,4)}

Score: {score}
Qty: {qty}
"""

        print(msg)

        send_telegram(msg)

    except Exception as e:

        error_msg = f"❌ Trade error {symbol}\n{str(e)}"

        print(error_msg)

        send_telegram(error_msg)


def bot_loop():

    print("🤖 BOT V5 démarré")

    while True:

        for symbol in SYMBOLS:

            try:

                print(f"⏳ Analyse {symbol}")

                df = fetch_ohlcv(symbol)

                df = apply_indicators(df)

                signal, score, atr = check_signal(df)

                print(f"🚦 Signal {symbol} = {signal} | Score={score}")

                if signal is None:
                    continue

                if score < SCORE_THRESHOLD:
                    print("⚠️ Signal rejeté")
                    continue

                price = df.close.iloc[-1]

                side = "buy" if signal == "long" else "sell"

                place_trade(symbol, side, price, atr, score)

                signals_log.append({
                    "symbol": symbol,
                    "signal": signal,
                    "score": score,
                    "price": price
                })

            except Exception as e:

                print("Erreur bot:", e)

        time.sleep(60)


def start_api():

    print("🌐 API server started on port 5001")

    app.run(host="0.0.0.0", port=5001)


if __name__ == "__main__":

    threading.Thread(target=start_api).start()

    bot_loop()