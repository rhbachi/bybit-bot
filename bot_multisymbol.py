import os
import time
import threading
import pandas as pd
from datetime import datetime, timezone
from flask import Flask, jsonify

from config import exchange, SYMBOLS
from strategy import apply_indicators, check_signal
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade
from database import init_db, insert_trade, get_recent_trades


# =========================
# FLASK API (HEDGE FUND)
# =========================
app = Flask(__name__)
@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "bot": "MULTI_SYMBOL"})


@app.route("/api/signals")
def api_signals():
    try:
        return jsonify(get_recent_trades(50))
    except Exception as e:
        print(f"❌ API error: {e}", flush=True)
        return jsonify([])


def run_api():
    print("🌐 API server started on port 5001", flush=True)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)


# =========================
# ENV PARAMETERS
# =========================
CAPITAL = float(os.getenv("CAPITAL", 50))
LEVERAGE = int(os.getenv("LEVERAGE", 3))
TIMEFRAME = os.getenv("TIMEFRAME", "15m")
PAPER_TRADING = os.getenv("PAPER_TRADING", "false").lower() == "true"
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", 2))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", 0.02))
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", 300))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", 10)) / 100
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", 3))
SL_ATR_MULTIPLIER = float(os.getenv("SL_ATR_MULTIPLIER", 1.5))
TP_ATR_MULTIPLIER = float(os.getenv("TP_ATR_MULTIPLIER", 3.0))

# =========================
state = {}
current_day = datetime.now(timezone.utc).date()
daily_loss = 0.0
consecutive_losses = 0

def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except:
        return default

def init_symbol_state(symbol):
    state[symbol] = {
        "in_position": False,
        "last_trade_time": None,
        "entry_price": 0,
        "qty": 0,
        "side": None,
        "sl": 0,
        "tp": 0,
    }

def reset_daily():
    global current_day, daily_loss, consecutive_losses
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        current_day = today
        daily_loss = 0.0
        consecutive_losses = 0
        print("🔄 Nouveau jour", flush=True)


def fetch_data(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=200)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"],
    )


def get_open_positions():
    positions = exchange.fetch_positions()
    return [
        p for p in positions
        if safe_float(p.get("contracts")) > 0
    ]


# =========================
def run():
    global daily_loss, consecutive_losses

    print("🤖 MultiSymbol Bot PRO (HEDGE FUND PHASE 1)", flush=True)
    send_telegram("🤖 MultiSymbol Bot PRO démarré")
    init_logger()
    init_db()

    for symbol in SYMBOLS:
        init_symbol_state(symbol)

    while True:
        try:
            reset_daily()

            if daily_loss >= CAPITAL * MAX_DAILY_LOSS_PCT:
                print("🛑 Daily loss limit reached", flush=True)
                time.sleep(600)
                continue

            if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                print("🛑 Max consecutive losses reached", flush=True)
                time.sleep(600)
                continue

            for symbol in SYMBOLS:

                s = state[symbol]

                if s["last_trade_time"] and time.time() - s["last_trade_time"] < COOLDOWN_SECONDS:
                    continue

                open_positions = get_open_positions()
                if len(open_positions) >= MAX_POSITIONS:
                    continue

                df = fetch_data(symbol)
                df = apply_indicators(df)

                signal, score = check_signal(df)

                if score < SCORE_THRESHOLD:
                print(f"⚠️ Signal rejeté | Score={score}")
                   continue

                signal = check_signal(df)

                print(f"⏳ Analyse {symbol} | Signal={signal}", flush=True)

                if signal and not s["in_position"]:

                    price = df.iloc[-1].close
                    atr = df["high"].rolling(14).max() - df["low"].rolling(14).min()
                    atr_value = atr.iloc[-1]

                    stop_distance = atr_value * SL_ATR_MULTIPLIER
                    tp_distance = atr_value * TP_ATR_MULTIPLIER

                    if signal == "long":
                        stop_loss = price - stop_distance
                        take_profit = price + tp_distance
                        side = "LONG"
                    else:
                        stop_loss = price + stop_distance
                        take_profit = price - tp_distance
                        side = "SHORT"

                    qty = calculate_position_size(
                        CAPITAL,
                        RISK_PER_TRADE,
                        stop_distance / price,
                        price,
                        LEVERAGE,
                    )

                    if qty <= 0:
                        continue

                    stop_loss = float(exchange.price_to_precision(symbol, stop_loss))
                    take_profit = float(exchange.price_to_precision(symbol, take_profit))
                    qty = float(exchange.amount_to_precision(symbol, qty))

                    if not PAPER_TRADING:
                        exchange.create_market_order(
                            symbol,
                            "buy" if signal == "long" else "sell",
                            qty,
                        )

                    s["in_position"] = True
                    s["last_trade_time"] = time.time()
                    s["entry_price"] = price
                    s["qty"] = qty
                    s["side"] = signal
                    s["sl"] = stop_loss
                    s["tp"] = take_profit

                    print(f"📈 TRADE OUVERT {symbol} {side}", flush=True)

                # ===== CHECK CLOSE =====
                if s["in_position"]:

                    current_price = df.iloc[-1].close

                    exit_condition = False

                    if s["side"] == "long":
                        if current_price <= s["sl"] or current_price >= s["tp"]:
                            exit_condition = True
                    else:
                        if current_price >= s["sl"] or current_price <= s["tp"]:
                            exit_condition = True

                    if exit_condition:

                        if s["side"] == "long":
                            pnl = (current_price - s["entry_price"]) * s["qty"]
                        else:
                            pnl = (s["entry_price"] - current_price) * s["qty"]

                        result = "WIN" if pnl > 0 else "LOSS"

                        insert_trade(
                            symbol=symbol,
                            side=s["side"],
                            entry=s["entry_price"],
                            exit_price=current_price,
                            sl=s["sl"],
                            tp=s["tp"],
                            qty=s["qty"],
                            pnl=pnl,
                            result=result
                        )

                        if pnl < 0:
                            daily_loss += abs(pnl)
                            consecutive_losses += 1
                        else:
                            consecutive_losses = 0

                        log_trade(symbol, "CLOSED", 0, 0, 0, pnl, result)

                        s["in_position"] = False

                        print(f"📊 CLOSE {symbol} | PnL={pnl}", flush=True)

            time.sleep(30)

        except Exception as e:
            print("❌ Bot Error:", e, flush=True)
            time.sleep(60)


# =========================
# START API THREAD
# =========================
threading.Thread(target=run_api, daemon=True).start()

# =========================
run()