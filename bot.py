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
from notifier import send_telegram
from logger import init_logger, log_trade

# =========================
# PARAMÈTRES STRATÉGIE
# =========================
STOP_LOSS_PCT = 0.006      # 0.6%
TAKE_PROFIT_PCT = 0.009   # 0.9%

MAX_TRADES_PER_DAY = 10
MAX_DAILY_LOSS_PCT = 0.20

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


def enforce_min_qty(symbol, qty):
    if "BTC" in symbol:
        return max(qty, 0.001)
    if "ETH" in symbol:
        return max(qty, 0.01)
    return qty


# =========================
# LOGGING CLÔTURE TRADE
# =========================
def check_trade_closed():
    global in_position, daily_loss

    positions = exchange.fetch_positions([SYMBOL])
    pos = next((p for p in positions if p["symbol"] == SYMBOL), None)

    if in_position and pos and float(pos.get("contracts", 0)) == 0:
        pnl = float(pos.get("realizedPnl", 0))
        entry = float(pos.get("entryPrice", 0))
        exit_price = float(pos.get("markPrice", 0))

        result = "WIN" if pnl > 0 else "LOSS"

        log_trade(
            symbol=SYMBOL,
            side=result,
            qty=0,
            entry=entry,
            exit_price=exit_price,
            pnl=pnl,
            result=result
        )

        if pnl < 0:
            daily_loss += abs(pnl)

        in_position = False

        msg = f"📊 TRADE CLOSED | Result={result} | PnL={pnl} USDT"
        print(msg, flush=True)
        send_telegram(msg)


# =========================
# EXECUTION TRADE (BYBIT V5)
# =========================
def place_trade(signal, qty, entry_price):
    global in_position, trades_today

    side = "buy" if signal == "long" else "sell"

    if signal == "long":
        stop_loss = entry_price * (1 - STOP_LOSS_PCT)
        take_profit = entry_price * (1 + TAKE_PROFIT_PCT)
    else:
        stop_loss = entry_price * (1 + STOP_LOSS_PCT)
        take_profit = entry_price * (1 - TAKE_PROFIT_PCT)

    exchange.create_market_order(
        symbol=SYMBOL,
        side=side,
        amount=qty,
        params={
            "stopLoss": stop_loss,
            "takeProfit": take_profit,
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice"
        }
    )

    in_position = True
    trades_today += 1

    msg = (
        f"✅ *TRADE {signal.upper()}*\n"
        f"Pair: {SYMBOL}\n"
        f"Qty: {qty}\n"
        f"Entry: {round(entry_price,2)}\n"
        f"SL: {round(stop_loss,2)}\n"
        f"TP: {round(take_profit,2)}"
    )

    print(msg, flush=True)
    send_telegram(msg)


# =========================
# MAIN LOOP (24/7 SAFE)
# =========================
def run():
    global in_position, daily_loss

    print("🤖 Bot lancé (BYBIT MAINNET – V5)", flush=True)
    send_telegram("🤖 Bot Bybit V5 démarré")

    # 👉 INIT LOGGER CSV
    init_logger()

    # Leverage (safe)
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"🔒 Leverage x{LEVERAGE} activé", flush=True)
    except Exception as e:
        if "leverage not modified" in str(e):
            print(f"ℹ️ Leverage déjà à x{LEVERAGE}", flush=True)
        else:
            send_telegram(f"⚠️ Erreur set_leverage: {e}")

    while True:
        try:
            reset_daily_counters()

            if daily_loss >= CAPITAL * MAX_DAILY_LOSS_PCT:
                send_telegram("🛑 Kill switch journalier – bot en pause")
                time.sleep(3600)
                continue

            if trades_today >= MAX_TRADES_PER_DAY:
                time.sleep(1800)
                continue

            df = fetch_data()
            df = apply_indicators(df)
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
                qty = enforce_min_qty(SYMBOL, qty)

                if qty > 0:
                    place_trade(signal, qty, price)

            # 👉 CHECK CLOTURE TRADE
            check_trade_closed()

            time.sleep(300)

        except Exception as e:
            print("❌ Erreur bot (non bloquante):", e, flush=True)
            send_telegram(f"❌ Erreur bot (non bloquante): {e}")
            time.sleep(60)


# =========================
# ENTRY POINT
# =========================
run()
