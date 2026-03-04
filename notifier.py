import time
import threading
import pandas as pd
from flask import Flask, jsonify

from config import (
    exchange,
    SYMBOLS,
    TIMEFRAME,
    CAPITAL,
    LEVERAGE,
    RISK_PER_TRADE,
    MAX_POSITIONS,
    SCORE_THRESHOLD
)

from strategy import apply_indicators, check_signal
from notifier import send_telegram


signals_memory = []
positions = {}

app = Flask(__name__)


# =========================
# API DASHBOARD
# =========================

@app.route("/api/signals")
def api_signals():
    return jsonify(signals_memory[-50:])


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


def start_api():
    print("🌐 API server started on port 5001", flush=True)
    app.run(host="0.0.0.0", port=5001)


# =========================
# MARKET DATA
# =========================

def get_ohlcv(symbol):

    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)

    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )

    return df


# =========================
# POSITION SIZE
# =========================

def calculate_position(symbol, price):

    risk_amount = CAPITAL * RISK_PER_TRADE
    position_value = risk_amount * LEVERAGE

    qty = position_value / price

    market = exchange.market(symbol)

    precision = market["precision"]["amount"]

    qty = round(qty, precision)

    if qty <= 0:
        return None

    return qty


# =========================
# PLACE TRADE
# =========================

def place_trade(symbol, side, price, score):

    if len(positions) >= MAX_POSITIONS:

        print("⚠️ Max positions atteint", flush=True)
        send_telegram(f"⚠️ Max positions atteint\nSignal ignoré: {symbol}")

        return

    qty = calculate_position(symbol, price)

    if qty is None:

        print("❌ Qty invalide", flush=True)
        return

    try:

        order = exchange.create_order(
            symbol=symbol,
            type="market",
            side="buy" if side == "long" else "sell",
            amount=qty,
        )

        positions[symbol] = order

        message = (
            f"📈 TRADE OPEN\n"
            f"Symbol: {symbol}\n"
            f"Direction: {side.upper()}\n"
            f"Qty: {qty}\n"
            f"Price: {price}\n"
            f"Score: {score}"
        )

        print(message, flush=True)

        send_telegram(message)

    except Exception as e:

        print("❌ Erreur MultiSymbol:", e, flush=True)
        send_telegram(f"❌ Trade error\n{symbol}\n{str(e)}")


# =========================
# ANALYSE
# =========================

def analyse_symbol(symbol):

    try:

        print(f"⏳ Analyse {symbol}", flush=True)

        df = get_ohlcv(symbol)

        df = apply_indicators(df)

        signal, score = check_signal(df)

        print(
            f"🚦 Signal {symbol} = {signal} | Score={score}",
            flush=True
        )

        if signal is None:
            return

        if score < SCORE_THRESHOLD:

            print(
                f"⚠️ Signal rejeté | Score={score}",
                flush=True
            )

            return

        price = df.close.iloc[-1]

        signals_memory.append({
            "symbol": symbol,
            "signal": signal,
            "score": score,
            "price": price
        })

        place_trade(symbol, signal, price, score)

    except Exception as e:

        print("❌ Analyse error:", e, flush=True)


# =========================
# BOT LOOP
# =========================

def bot_loop():

    send_telegram("🤖 MultiSymbol Bot V3 démarré")

    print("🤖 MultiSymbol Bot V3 démarré", flush=True)

    while True:

        for symbol in SYMBOLS:

            analyse_symbol(symbol)

            time.sleep(2)

        time.sleep(30)


# =========================
# START
# =========================

if __name__ == "__main__":

    api_thread = threading.Thread(target=start_api)

    api_thread.daemon = True

    api_thread.start()

    bot_loop()