import time
import pandas as pd
from datetime import datetime, timezone

from config import exchange, SYMBOL, TIMEFRAME, CAPITAL, RISK_PER_TRADE, LEVERAGE
from strategy import apply_indicators, check_signal
from risk import calculate_position_size

# === STRATEGY PARAMS ===
STOP_LOSS_PCT = 0.006     # 0.6%
TAKE_PROFIT_PCT = 0.009  # 0.9%

MAX_TRADES_PER_DAY = 10
MAX_DAILY_LOSS_PCT = 0.20

# === STATE ===
in_position = False
trades_today = 0
daily_loss = 0.0
current_day = datetime.now(timezone.utc).date()


def reset_daily_counters():
    global trades_today, daily_loss, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        daily_loss = 0.0
        current_day = today
        print("🔄 Nouveau jour → compteurs reset", flush=True)


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    df = pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )
    return df


def place_trade(signal, qty, entry_price):
    global in_position, trades_today

    side = "buy" if signal == "long" else "sell"

    # Market Order
    exchange.create_market_order(SYMBOL, side, qty)

    # SL / TP
    if signal == "long":
        sl = entry_price * (1 - STOP_LOSS_PCT)
        tp = entry_price * (1 + TAKE_PROFIT_PCT)
        exit_side = "sell"
    else:
        sl = entry_price * (1 + STOP_LOSS_PCT)
        tp = entry_price * (1 - TAKE_PROFIT_PCT)
        exit_side = "buy"

    # Stop Loss
    exchange.create_order(
        SYMBOL,
        "stop",
        exit_side,
        qty,
        None,
        {"stopPrice": sl}
    )

    # Take Profit
    exchange.create_limit_order(
        SYMBOL,
        exit_side,
        qty,
        tp
    )

    in_position = True
    trades_today += 1

    print(
        f"✅ TRADE {signal.upper()} | Qty={qty} | Entry={round(entry_price,2)} "
        f"| SL={round(sl,2)} | TP={round(tp,2)}",
        flush=True
    )


def run():
    global in_position, daily_loss

    print("🤖 Bot lancé (BYBIT MAINNET – LINEAR BTCUSDT)", flush=True)

    # Leverage (Linear only)
    exchange.set_leverage(LEVERAGE, SYMBOL)
    print(f"🔒 Leverage x{LEVERAGE} activé", flush=True)

    while True:
        try:
            reset_daily_counters()

            if daily_loss >= CAPITAL * MAX_DAILY_LOSS_PCT:
                print("🛑 KILL SWITCH – perte journalière max atteinte", flush=True)
                break

            if trades_today >= MAX_TRADES_PER_DAY:
                print("🛑 Max trades journaliers atteint", flush=True)
                time.sleep(300)
                continue

            df = apply_indicators(fetch_data())
            signal = check_signal(df)

            print("⏳ Analyse marché...", flush=True)

            if signal and not in_position:
                price = df.iloc[-1].close

                qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    STOP_LOSS_PCT,
                    price,
                    LEVERAGE
                )

                if qty > 0:
                    place_trade(signal, qty, price)

            time.sleep(300)

        except Exception as e:
            print("❌ Erreur:", e, flush=True)
            time.sleep(60)


run()
