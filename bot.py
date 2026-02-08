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
STOP_LOSS_PCT = 0.006
RR_MULTIPLIER = 2.3
MAX_TRADES_PER_DAY = 10
MAX_DAILY_LOSS_PCT = 0.20
COOLDOWN_SECONDS = 600

# =========================
# ÉTAT GLOBAL
# =========================
in_position = False
trades_today = 0
daily_loss = 0.0
current_day = datetime.now(timezone.utc).date()

last_trade_time = None
open_trade_ts = None
open_trade_side = None
open_trade_qty = None
open_trade_entry = None

# =========================
# UTILS
# =========================
def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def reset_daily():
    global trades_today, daily_loss, current_day
    today = datetime.now(timezone.utc).date()
    if today != current_day:
        trades_today = 0
        daily_loss = 0.0
        current_day = today
        send_telegram("🔄 Nouveau jour – compteurs réinitialisés")


def fetch_data():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
    return pd.DataFrame(
        ohlcv, columns=["time", "open", "high", "low", "close", "volume"]
    )


# =========================
# TRADE OPEN
# =========================
def place_trade(signal, qty, entry):
    global in_position, trades_today
    global open_trade_ts, open_trade_side, open_trade_qty, open_trade_entry

    side = "buy" if signal == "long" else "sell"

    if signal == "long":
        sl = entry * (1 - STOP_LOSS_PCT)
        tp = entry + (entry - sl) * RR_MULTIPLIER
    else:
        sl = entry * (1 + STOP_LOSS_PCT)
        tp = entry - (sl - entry) * RR_MULTIPLIER

    exchange.create_market_order(
        SYMBOL,
        side,
        qty,
        params={
            "stopLoss": sl,
            "takeProfit": tp,
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice",
        },
    )

    in_position = True
    trades_today += 1

    open_trade_ts = exchange.milliseconds()
    open_trade_side = side
    open_trade_qty = qty
    open_trade_entry = entry

    msg = (
        f"📈 TRADE OUVERT\n"
        f"Pair: {SYMBOL}\n"
        f"Direction: {signal.upper()}\n"
        f"Qty: {qty}\n"
        f"Entry: {round(entry, 2)}\n"
        f"SL: {round(sl, 2)}\n"
        f"TP: {round(tp, 2)}\n"
        f"RR: {RR_MULTIPLIER}"
    )
    send_telegram(msg)
    print(msg, flush=True)


# =========================
# TRADE CLOSE (PRO V5)
# =========================
def check_trade_closed():
    global in_position, daily_loss, last_trade_time
    global open_trade_ts, open_trade_side, open_trade_qty, open_trade_entry

    if not in_position:
        return

    trades = exchange.fetch_my_trades(SYMBOL, since=open_trade_ts)

    if not trades:
        return

    close_trades = [t for t in trades if t["side"] != open_trade_side]

    if not close_trades:
        return

    close_price = safe_float(close_trades[-1]["price"])
    fee = sum(safe_float(t.get("fee", {}).get("cost")) for t in close_trades)

    if open_trade_side == "buy":
        pnl = (close_price - open_trade_entry) * open_trade_qty
    else:
        pnl = (open_trade_entry - close_price) * open_trade_qty

    pnl -= fee
    result = "WIN" if pnl > 0 else "LOSS"

    log_trade(
        symbol=SYMBOL,
        side=open_trade_side,
        qty=open_trade_qty,
        entry=open_trade_entry,
        exit_price=close_price,
        pnl=pnl,
        result=result,
    )

    if pnl < 0:
        daily_loss += abs(pnl)

    msg = (
        f"📊 TRADE FERMÉ\n"
        f"Pair: {SYMBOL}\n"
        f"Résultat: {result}\n"
        f"PnL: {round(pnl, 2)} USDT"
    )
    send_telegram(msg)
    print(msg, flush=True)

    in_position = False
    last_trade_time = time.time()

    open_trade_ts = None
    open_trade_side = None
    open_trade_qty = None
    open_trade_entry = None


# =========================
# MAIN LOOP
# =========================
def run():
    global daily_loss

    print("🤖 Bot lancé (BYBIT MAINNET – PRO V5)", flush=True)
    send_telegram("🤖 Bot Bybit PRO V5 démarré")

    init_logger()

    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
    except Exception:
        pass

    while True:
        try:
            reset_daily()

            if daily_loss >= CAPITAL * MAX_DAILY_LOSS_PCT:
                send_telegram("🛑 Kill switch journalier activé")
                time.sleep(3600)
                continue

            if last_trade_time and time.time() - last_trade_time < COOLDOWN_SECONDS:
                time.sleep(30)
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

                qty = calculate_position_size(
                    CAPITAL,
                    RISK_PER_TRADE,
                    STOP_LOSS_PCT,
                    price,
                    LEVERAGE,
                )

                if qty > 0:
                    place_trade(signal, qty, price)

            check_trade_closed()
            time.sleep(300)

        except Exception as e:
            print("❌ Erreur bot:", e, flush=True)
            send_telegram(f"❌ Erreur bot: {e}")
            time.sleep(60)


run()
