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

from strategy import apply_indicators, check_signal
from risk import calculate_position_size

# =========================
# PARAMÈTRES STRATÉGIE
# =========================
STOP_LOSS_PCT = 0.006     # 0.6%
TAKE_PROFIT_PCT = 0.009  # 0.9%

MAX_TRADES_PER_DAY = 10
MAX_DAILY_LOSS_PCT = 0.20  # 20% du capital

# =========================
# ÉTAT GLOBAL
# =========================
in_position = False
trades_today = 0
daily_loss = 0.0
current_day = datetime.now(timezone.utc).date()

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

    # ---- ORDRE MARKET ----
    exchange.create_market_order(
        symbol=SYMBOL,
        side=side,
        amount=qty
    )

    # ---- SL / TP ----
    if signal == "long":
        stop_loss = entry_price * (1 - STOP_LOSS_PCT)
        take_profit = entry_price * (1 + TAKE_PROFIT_PCT)
        exit_side = "sell"
    else:
        stop_loss = entry_price * (1 + STOP_LOSS_PCT)
        take_profit = entry_price * (1 - TAKE_PROFIT_PCT)
        exit_side = "buy"

    # Stop Loss
    exchange.create_order(
        symbol=SYMBOL,
        type="stop",
        side=exit_side,
        amount=qty,
        price=None,
        params={"stopPrice": stop_loss}
    )

    # Take Profit
    exchange.create_limit_order(
        symbol=SYMBOL,
        side=exit_side,
        amount=qty,
        price=take_profit
    )

    in_position = True
    trades_today += 1

    print(
        f"✅ TRADE {signal.upper()} | Qty={qty} | Entry={round(entry_price,2)} "
        f"| SL={round(stop_loss,2)} | TP={round(take_profit,2)}",
        flush=True
    )


# =========================
# MAIN LOOP (24/7 SAFE)
# =========================
def run():
    global in_position, daily_loss

    print("🤖 Bot lancé (BYBIT MAINNET – LINEAR BTCUSDT)", flush=True)

    # Levier (Linear only)
    exchange.set_leverage(LEVERAGE, SYMBOL)
    print(f"🔒 Leverage x{LEVERAGE} activé", flush=True)

    while True:
        try:
            reset_daily_counters()

            # 🛑 KILL SWITCH SÉCURITÉ (SANS ARRÊTER LE BOT)
            if daily_loss >= CAPITAL * MAX_DAILY_LOSS_PCT:
                print(
                    "🛑 KILL SWITCH – perte journalière max atteinte "
                    "(bot en pause, pas d'arrêt)",
                    flush=True
                )
                # Pause longue, mais le process reste vivant
                time.sleep(3600)
                continue

            # Limite de trades journaliers
            if trades_today >= MAX_TRADES_PER_DAY:
                print("🛑 Max trades journaliers atteint – pause", flush=True)
                time.sleep(1800)
                continue

            df = fetch_data()
            df = apply_indicators(df)
            signal = check_signal(df)

            print("⏳ Analyse marché...", flush=True)

            if signal and not in_position:
                price = df.iloc[-1].close

                qty = calculate_position_size(
                    capital=CAPITAL,
                    risk_pct=RISK_PER_TRADE,
                    stop_loss_pct=STOP_LOSS_PCT,
                    price=price,
                    leverage=LEVERAGE
                )

                if qty > 0:
                    place_trade(signal, qty, price)
                else:
                    print("⚠️ Quantité invalide, trade ignoré", flush=True)

            # Timeframe 5 minutes
            time.sleep(300)

        except Exception as e:
            # ❗ NE JAMAIS QUITTER LE PROCESS
            print("❌ Erreur attrapée (bot continue):", e, flush=True)
            time.sleep(60)


# =========================
# ENTRY POINT
# =========================
run()
