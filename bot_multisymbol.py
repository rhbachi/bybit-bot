import os
import time
import pandas as pd
from datetime import datetime, timezone

from config import exchange, SYMBOLS
from strategy import apply_indicators, check_signal
from risk import calculate_position_size
from notifier import send_telegram
from logger import init_logger, log_trade


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

TRAILING_STOP_ACTIVATION = float(os.getenv("TRAILING_STOP_ACTIVATION", 0.01))
TRAILING_STOP_DISTANCE = float(os.getenv("TRAILING_STOP_DISTANCE", 0.005))

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


def run():
    global daily_loss, consecutive_losses

    print("🤖 MultiSymbol Bot PRO démarré", flush=True)
    send_telegram("🤖 MultiSymbol Bot PRO démarré")
    init_logger()

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
                    else:
                        stop_loss = price + stop_distance
                        take_profit = price - tp_distance

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
                            params={
                                "stopLoss": stop_loss,
                                "takeProfit": take_profit,
                                "slTriggerBy": "LastPrice",
                                "tpTriggerBy": "LastPrice",
                            },
                        )

                    s["in_position"] = True
                    s["last_trade_time"] = time.time()

                    print(
                        f"📈 TRADE | {symbol} | {signal.upper()} | "
                        f"SL={stop_loss} | TP={take_profit} | Qty={qty}",
                        flush=True,
                    )

                # ===== CHECK CLOSE =====
                positions = exchange.fetch_positions([symbol])
                pos = next((p for p in positions if p.get("symbol") == symbol), None)

                if s["in_position"] and pos and safe_float(pos.get("contracts")) == 0:
                    pnl = safe_float(pos.get("realizedPnl"))

                    if pnl < 0:
                        daily_loss += abs(pnl)
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0

                    log_trade(symbol, "CLOSED", 0, 0, 0, pnl, "CLOSED")
                    s["in_position"] = False

                    print(f"📊 CLOSE {symbol} | PnL={pnl}", flush=True)

            time.sleep(60)

        except Exception as e:
            print("❌ Bot Error:", e, flush=True)
            time.sleep(60)


run()