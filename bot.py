import time
import pandas as pd
from datetime import datetime, timezone

from config import (
    exchange,
    SYMBOL,
    TIMEFRAME,
    CAPITAL,
    RISK_PER_TRADE,
    LEVERAGE,
)

from notifier import send_telegram
from risk import calculate_position_size

# =========================
# PARAMÈTRES STRATÉGIE
# =========================
STOP_LOSS_PCT = 0.006     # 0.6%
TAKE_PROFIT_PCT = 0.009  # 0.9%

MAX_TRADES_PER_DAY = 15
MAX_DAILY_LOSS_PCT = 0.20  # 20%

# =========================
# ÉTAT GLOBAL
# =========================
in_position = False
trades_today = 0
daily_loss = 0.0
current_day = datetime.now(timezone.utc).date()

# =========================
# INDICATEURS
# =========================
def apply_indicators(df):
    # EMA plus rapides
    df["ema7"] = df["close"].ewm(span=7, adjust=False).mean()
    df["ema14"] = df["close"].ewm(span=14, adjust=False).mean()

    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    return df


def check_signal(df):
    if len(df) < 20:
        return None

    last = df.iloc[-1]

    # LONG plus permissif
    if last.ema7 > last.ema14 and 45 <= last.rsi <= 70:
        return "long"

    # SHORT plus permissif
    if last.ema7 < last.ema14 and 30 <= last.rsi <= 55:
        return "short"

    return None

# =========================
# UTILITAIRES
# =========================
def reset_daily_counters():
    global trades_today, daily_loss, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        daily_loss = 0.0
        current_day = today
        print("🔄 Nouveau jour → compteurs réinitialisés", flush=True)
        send_telegram("🔄 Nouveau jour → compteurs réinitialisés")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    return pd.DataFrame(
        ohlcv,
        columns=["time", "open", "high", "low", "close", "volume"]
    )


def get_safe_position_size(price):
    balance = exchange.fetch_balance()
    usdt_free = balance["USDT"]["free"]

    max_position_value = usdt_free * LEVERAGE * 0.9
    qty = max_position_value / price

    return round(qty, 4)


def place_trade(signal, qty, entry_price):
    global in_position, trades_today

    side = "buy" if signal == "long" else "sell"
    exchange.create_market_order(SYMBOL, side, qty)

    if signal == "long":
        sl = entry_price * (1 - STOP_LOSS_PCT)
        tp = entry_price * (1 + TAKE_PROFIT_PCT)
        exit_side = "sell"
    else:
        sl = entry_price * (1 + STOP_LOSS_PCT)
        tp = entry_price * (1 - TAKE_PROFIT_PCT)
        exit_side = "buy"

    exchange.create_order(
        SYMBOL,
        "stop",
        exit_side,
        qty,
        None,
        {"stopPrice": sl}
    )

    exchange.create_limit_order(SYMBOL, exit_side, qty, tp)

    in_position = True
    trades_today += 1

    msg = (
        f"✅ *TRADE {signal.upper()}*\n"
        f"Pair: {SYMBOL}\n"
        f"Qty: {qty}\n"
        f"Entry: {round(entry_price,2)}\n"
        f"SL: {round(sl,2)}\n"
        f"TP: {round(tp,2)}"
    )

    print(msg, flush=True)
    send_telegram(msg)

# =========================
# MAIN LOOP
# =========================
def run():
    global in_position, daily_loss

    print("🤖 Bot lancé (BYBIT MAINNET – BTCUSDT)", flush=True)
    send_telegram("🤖 Bot démarré (stratégie assouplie)")

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
    except Exception as e:
        if "leverage not modified" in str(e):
            print(f"ℹ️ Leverage déjà à x{LEVERAGE}", flush=True)
        else:
            send_telegram(f"⚠️ Erreur set_leverage: {e}")

    while True:
        try:
            reset_daily_counters()

            if daily_loss >= CAPITAL * MAX_DAILY_LOSS_PCT:
                send_telegram("🛑 Kill switch journalier – pause")
                time.sleep(3600)
                continue

            if trades_today >= MAX_TRADES_PER_DAY:
                time.sleep(1800)
                continue

            df = apply_indicators(fetch_data())
            signal = check_signal(df)

            print("⏳ Analyse marché...", flush=True)

            if signal and not in_position:
                price = df.iloc[-1].close

                theoretical_qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    STOP_LOSS_PCT,
                    price,
                    LEVERAGE
                )

                safe_qty = get_safe_position_size(price)
                qty = min(theoretical_qty, safe_qty)

                if qty > 0:
                    place_trade(signal, qty, price)

            time.sleep(300)

        except Exception as e:
            print("❌ Erreur attrapée:", e, flush=True)
            send_telegram(f"❌ Erreur bot: {e}")
            time.sleep(60)

# =========================
# ENTRY
# =========================
run()
